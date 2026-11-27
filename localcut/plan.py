"""Edit plan: the text the cloud model sends back. Validated locally before anything is rendered.

{
  "title": "島へ渡った日",
  "target_sec": 45,
  "cuts": [{"shot": "C01-S00", "in": 1.0, "out": 5.5, "telop": "いよいよ出航"}, ...],
  "thumbnail": {"shot": "C09-S03"}
}
"""

from __future__ import annotations

import json
from dataclasses import dataclass

MAX_TELOP_CHARS = 18
MAX_TITLE_CHARS = 40


@dataclass
class Cut:
    shot: str
    clip: str
    start: float
    end: float
    telop: str

    @property
    def length(self) -> float:
        return self.end - self.start


@dataclass
class Plan:
    title: str
    target_sec: float
    cuts: list[Cut]
    thumbnail_shot: str | None

    @property
    def duration(self) -> float:
        return sum(c.length for c in self.cuts)


def validate(plan_json: str | dict, shots: list[dict]) -> tuple[Plan | None, list[str]]:
    """Return (plan, problems). `shots` come from brief.load_shots (local)."""
    problems: list[str] = []
    try:
        data = json.loads(plan_json) if isinstance(plan_json, str) else plan_json
    except json.JSONDecodeError as e:
        return None, [f"plan is not valid JSON: {e}"]
    by_id = {s["shot"]: s for s in shots}
    clip_len = {}
    for s in shots:
        clip_len[s["clip"]] = max(clip_len.get(s["clip"], 0.0), s["end"])

    title = str(data.get("title", "")).strip()
    if not title:
        problems.append("title is empty")
    elif len(title) > MAX_TITLE_CHARS:
        problems.append(f"title is longer than {MAX_TITLE_CHARS} chars")

    cuts: list[Cut] = []
    for i, c in enumerate(data.get("cuts") or []):
        sid = str(c.get("shot", ""))
        shot = by_id.get(sid)
        if not shot:
            problems.append(f"cut {i}: unknown shot {sid!r}")
            continue
        start = float(c.get("in", shot["start"]))
        end = float(c.get("out", shot["end"]))
        if not (0 <= start < end <= clip_len[shot["clip"]] + 0.05):
            problems.append(f"cut {i}: in/out {start}-{end} is outside clip {shot['clip']} (0-{clip_len[shot['clip']]:.1f})")
            continue
        if end - start < 0.8:
            problems.append(f"cut {i}: shorter than 0.8s")
        telop = str(c.get("telop", "") or "").strip()
        if len(telop) > MAX_TELOP_CHARS:
            problems.append(f"cut {i}: telop longer than {MAX_TELOP_CHARS} chars")
        cuts.append(Cut(sid, shot["clip"], start, end, telop))
    if not cuts:
        problems.append("no valid cuts")

    target = float(data.get("target_sec") or 0)
    plan = Plan(title, target, cuts, (data.get("thumbnail") or {}).get("shot"))
    if target and cuts and abs(plan.duration - target) > max(3.0, 0.15 * target):
        problems.append(f"total {plan.duration:.1f}s is far from target_sec {target:.0f}s")
    if plan.thumbnail_shot and plan.thumbnail_shot not in by_id:
        problems.append(f"thumbnail shot {plan.thumbnail_shot!r} is unknown")
    return plan, problems
