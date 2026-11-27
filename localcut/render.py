"""Local render: edit plan -> vertical 1080x1920 MP4 with faces blurred and telops burned in.

Per cut: ffmpeg trims and frames the shot to 1080x1920 (landscape shots get a blurred
background), the frames are piped through Python for face blurring, then re-encoded.
Finally the cuts are concatenated and the telops (ASS subtitles) are burned in.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import numpy as np
from PIL import Image

from . import config, media
from .plan import Plan

W, H, FPS = 1080, 1920, 30
FONT = "BIZ UDGothic"


def _frame_filter(orientation: str) -> str:
    if orientation == "portrait":
        return f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},format=rgb24"
    return (f"split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=30:3[bg];"
            f"[b]scale={W}:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,fps={FPS},format=rgb24")


def _detect_region(probe: dict) -> tuple[int, int, int, int]:
    """Where the sharp picture is: the whole frame for portrait, the centre band for landscape.
    Detecting on that band (instead of the padded 1080x1920 frame) keeps small faces large enough."""
    if probe["orientation"] == "portrait":
        return (0, 0, W, H)
    h = int(round(W * probe["height"] / probe["width"]))
    top = (H - h) // 2
    return (0, top, W, top + h)


def _tiles(region: tuple[int, int, int, int]) -> list[tuple[int, int, int, int]]:
    """Landscape band (wide): two overlapping halves so small faces stay above YuNet's minimum size."""
    x0, y0, x1, y1 = region
    w, h = x1 - x0, y1 - y0
    if w <= h * 1.2:
        return [region]
    half = w // 2
    ov = int(w * 0.08)
    return [(x0, y0, x0 + half + ov, y1), (x0 + half - ov, y0, x1, y1)]


def _render_cut(src: Path, start: float, end: float, probe: dict, out: Path, blur_faces: bool,
                encoder: str) -> dict:
    orientation = probe["orientation"]
    region = _detect_region(probe)
    ff = media._tool("ffmpeg")
    dec = subprocess.Popen(
        [ff, "-hide_banner", "-loglevel", "error", "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", str(src),
         "-an", "-filter_complex", _frame_filter(orientation), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        stdout=subprocess.PIPE)
    enc_args = (["-c:v", "libx264", "-preset", "veryfast", "-crf", "21"] if encoder == "libx264"
                else ["-c:v", encoder, "-b:v", "8M"])
    enc = subprocess.Popen(
        [ff, "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-", *enc_args, "-pix_fmt", "yuv420p", str(out)],
        stdin=subprocess.PIPE)
    detector = None
    if blur_faces:
        from . import faces as detector  # noqa: N813
    frame_bytes = W * H * 3
    n = faces_total = 0
    last_faces: list = []
    while True:
        buf = dec.stdout.read(frame_bytes)
        if len(buf) < frame_bytes:
            break
        if detector:
            img = Image.frombuffer("RGB", (W, H), buf, "raw", "RGB", 0, 1)
            if n % 2 == 0:  # detect every other frame, reuse boxes in between
                found = []
                for x0, y0, x1, y1 in _tiles(region):
                    found += [detector.Face(f.x + x0, f.y + y0, f.w, f.h, f.score)
                              for f in detector.detect(img.crop((x0, y0, x1, y1)), score_threshold=0.55)]
                last_faces = detector.nms(found)
            if last_faces:
                faces_total += len(last_faces)
                buf = np.asarray(detector.blur(img, last_faces)).tobytes()
        enc.stdin.write(buf)
        n += 1
    enc.stdin.close()
    dec.wait()
    enc.wait()
    if enc.returncode != 0 or dec.returncode != 0:
        raise RuntimeError(f"render failed for {src.name} ({dec.returncode}/{enc.returncode})")
    return {"frames": n, "face_boxes": faces_total}


def _ass_time(t: float) -> str:
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def write_ass(plan: Plan, path: Path) -> None:
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV",
        f"Style: Telop,{FONT},84,&H00FFFFFF,&H00202020,&H64000000,-1,1,6,2,2,60,60,360",
        f"Style: Title,{FONT},104,&H00FFFFFF,&H00202020,&H64000000,-1,1,7,2,8,60,60,260",
        "", "[Events]", "Format: Layer, Start, End, Style, Text",
    ]
    t = 0.0
    for i, c in enumerate(plan.cuts):
        if i == 0 and plan.title:
            lines.append(f"Dialogue: 0,{_ass_time(0)},{_ass_time(min(c.length, 3.0))},Title,{plan.title}")
        if c.telop:
            lines.append(f"Dialogue: 0,{_ass_time(t + 0.2)},{_ass_time(t + c.length - 0.1)},Telop,{c.telop}")
        t += c.length
    path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")


def render(plan: Plan, render_id: str, quality: str = "draft", blur_faces: bool = True,
           encoder: str = "libx264", recorder=None) -> dict:
    work = config.WORK_DIR
    clips = json.loads((work / "clips.json").read_text(encoding="utf-8"))
    out_dir = work / "renders" / render_id
    (out_dir / "cuts").mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    parts = []
    for i, c in enumerate(plan.cuts):
        probe = json.loads((work / c.clip / "probe.json").read_text(encoding="utf-8"))
        part = out_dir / "cuts" / f"{i:03d}.mp4"
        ctx = recorder.stage("render_cut", c.clip) if recorder else _null()
        with ctx as m:
            info = _render_cut(Path(clips[c.clip]), c.start, c.end, probe, part, blur_faces, encoder)
            m.update(input_sec=c.length, **info)
        parts.append(part)
    (out_dir / "concat.txt").write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    write_ass(plan, out_dir / "telop.ass")
    final = out_dir / "final.mp4"
    ff = media._tool("ffmpeg")
    fonts = "C\\:/Windows/Fonts"
    ass = (out_dir / "telop.ass").as_posix().replace(":", "\\:")
    ctx = recorder.stage("render_final", None) if recorder else _null()
    with ctx as m:
        subprocess.run(
            [ff, "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(out_dir / "concat.txt"),
             "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
             "-vf", f"subtitles='{ass}':fontsdir='{fonts}'", "-c:v", "libx264", "-preset",
             "veryfast" if quality == "draft" else "medium", "-crf", "23" if quality == "draft" else "19",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", "-movflags", "+faststart", str(final)],
            check=True)
        m.update(input_sec=plan.duration)
    return {"render_id": render_id, "duration": round(plan.duration, 2), "cuts": len(parts),
            "render_sec": round(time.perf_counter() - t0, 1), "bytes": final.stat().st_size}


class _null:
    def __enter__(self):
        return {}

    def __exit__(self, *a):
        return False
