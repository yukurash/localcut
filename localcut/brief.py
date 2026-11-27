"""Build the edit brief: the only footage-derived text that is ever offered to the cloud.

One line per shot, built from an allow-list of caption fields. Paths, file names,
timestamps of the day, GPS and face coordinates are not part of the allow-list.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import config


def _mmss(t: float) -> str:
    return f"{int(t) // 60:02d}:{int(t) % 60:02d}"


def load_shots(work_dir: Path | None = None) -> list[dict]:
    work_dir = work_dir or config.WORK_DIR
    shots: list[dict] = []
    for cdir in sorted(p for p in work_dir.iterdir() if p.is_dir() and p.name.startswith("C")):
        cap = cdir / "captions.jsonl"
        if not cap.is_file():
            continue
        probe = json.loads((cdir / "probe.json").read_text(encoding="utf-8"))
        for line in cap.read_text(encoding="utf-8").splitlines():
            if line.strip():
                shot = json.loads(line)
                shot["clip"] = cdir.name
                shot["orientation"] = probe.get("orientation")
                shots.append(shot)
    return shots


def build_brief(shots: list[dict], detail: str = "normal") -> str:
    clips = sorted({s["clip"] for s in shots})
    total = 0.0
    for c in clips:
        total += max(s["end"] for s in shots if s["clip"] == c)
    portrait = len({s["clip"] for s in shots if s.get("orientation") == "portrait"})
    lines = [
        "# localcut edit brief v1 (shot = clip-segment; times are seconds within the clip)",
        f"clips={len(clips)} shots={len(shots)} total={_mmss(total)} portrait_clips={portrait}/{len(clips)}",
        "# shot | in-out | place | subject / action | mood | people | highlight | quality(4)",
    ]
    for s in shots:
        row = (f"{s['shot']} | {s['start']:.1f}-{s['end']:.1f} | {s['place']} | {s['subject']} / {s['action']} | "
               f"{s['mood']} | {s['people']} | {'★' * s['highlight']} | {s['quality']}/4")
        if detail == "full" and s.get("text_visible"):
            row += " | text-in-frame"
        lines.append(row)
    return "\n".join(lines) + "\n"
