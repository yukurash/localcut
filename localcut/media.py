"""ffmpeg / ffprobe helpers: probe, scene detection and keyframe extraction.

Everything here runs locally. Nothing in this module talks to the network.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import config


class ToolMissing(RuntimeError):
    pass


def _tool(name: str) -> str:
    path = config.find_tool(name)
    if not path:
        raise ToolMissing(f"{name} not found on PATH or under {config.TOOLS_DIR}")
    return path


@dataclass
class Probe:
    duration: float
    width: int
    height: int
    fps: float
    size_bytes: int
    has_audio: bool
    # Fields below are kept locally and never sent anywhere.
    creation_time: str | None = None
    has_location: bool = False
    tags: dict = field(default_factory=dict)

    @property
    def orientation(self) -> str:
        return "portrait" if self.height > self.width else "landscape"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["orientation"] = self.orientation
        return d


def _fps(rate: str) -> float:
    num, _, den = rate.partition("/")
    try:
        return float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        return 0.0


def probe(path: Path) -> Probe:
    out = subprocess.run(
        [_tool("ffprobe"), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, check=True, encoding="utf-8",
    ).stdout
    info = json.loads(out)
    video = next(s for s in info["streams"] if s.get("codec_type") == "video")
    fmt = info.get("format", {})
    tags = {**fmt.get("tags", {}), **video.get("tags", {})}
    has_location = any("location" in k.lower() or "gps" in k.lower() for k in tags)
    rotation = 0
    for sd in video.get("side_data_list", []) or []:
        if "rotation" in sd:
            rotation = abs(int(sd["rotation"]))
    w, h = int(video["width"]), int(video["height"])
    if rotation in (90, 270):
        w, h = h, w
    return Probe(
        duration=float(fmt.get("duration") or video.get("duration") or 0.0),
        width=w, height=h,
        fps=_fps(video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/1"),
        size_bytes=int(fmt.get("size") or path.stat().st_size),
        has_audio=any(s.get("codec_type") == "audio" for s in info["streams"]),
        creation_time=tags.get("creation_time"),
        has_location=has_location,
        tags=tags,
    )


_PTS = re.compile(r"pts_time:([0-9.]+)")


def scene_changes(path: Path, threshold: float = 0.3, analyze_width: int = 480) -> list[float]:
    """Timestamps (s) where ffmpeg's scene score exceeds `threshold`, measured on a downscaled stream."""
    proc = subprocess.run(
        [_tool("ffmpeg"), "-hide_banner", "-nostats", "-i", str(path), "-an",
         "-vf", f"scale={analyze_width}:-2,select='gt(scene,{threshold})',showinfo", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-2000:])
    return [float(m.group(1)) for line in proc.stderr.splitlines() if "showinfo" in line
            for m in [_PTS.search(line)] if m]


@dataclass
class Segment:
    index: int
    start: float
    end: float

    @property
    def mid(self) -> float:
        return (self.start + self.end) / 2

    @property
    def length(self) -> float:
        return self.end - self.start


def segments(duration: float, cuts: list[float], min_len: float = 1.5, max_len: float = 8.0,
             max_segments: int = 12) -> list[Segment]:
    """Turn scene-change timestamps into shot segments.

    - cuts closer than `min_len` to the previous boundary are dropped (merge tiny shots)
    - segments longer than `max_len` are split evenly (long pans still get several frames)
    - at most `max_segments` per clip: the shortest neighbours are merged first
    """
    bounds = [0.0]
    for t in sorted(c for c in cuts if 0.0 < c < duration):
        if t - bounds[-1] >= min_len and duration - t >= min_len:
            bounds.append(t)
    bounds.append(duration)
    spans: list[tuple[float, float]] = []
    for a, b in zip(bounds, bounds[1:]):
        n = max(1, int((b - a) // max_len) + (1 if (b - a) % max_len > 1e-6 else 0))
        step = (b - a) / n
        spans.extend((a + i * step, a + (i + 1) * step) for i in range(n))
    while len(spans) > max_segments:
        i = min(range(len(spans) - 1), key=lambda k: (spans[k][1] - spans[k][0]) + (spans[k + 1][1] - spans[k + 1][0]))
        spans[i:i + 2] = [(spans[i][0], spans[i + 1][1])]
    return [Segment(i, round(a, 3), round(b, 3)) for i, (a, b) in enumerate(spans)]


def extract_frame(path: Path, t: float, out: Path, width: int = 768) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [_tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.3f}", "-i", str(path),
         "-frames:v", "1", "-vf", f"scale='min({width},iw)':-2", "-q:v", "3", str(out)],
        check=True,
    )
    return out
