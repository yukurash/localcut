"""Local VLM shot captions: one JSON object per keyframe, written to work/<clip>/captions.jsonl.

The model sees the frame; only short words come out. Visible text (signs, shop names,
plates) is never transcribed: the model only reports whether text is visible.
The quality verdict follows the spark-vibe `visual_review` checklist idea: the model
reports per-item observations and the score is computed in code.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import config, lmstudio

QUALITY_ITEMS = ("in_focus", "well_exposed", "horizon_level", "subject_clear")

SYSTEM = (
    "You describe ONE frame from a personal travel video for a video editor who cannot see it. "
    "Reply with ONLY a JSON object with these keys:\n"
    '{"place": string, "subject": string, "action": string, "mood": string, "people": integer, '
    '"text_visible": boolean, "checks": {"in_focus": bool, "well_exposed": bool, "horizon_level": bool, '
    '"subject_clear": bool}, "highlight": integer 1-5}\n'
    "Rules:\n"
    "- Write place/subject/action/mood in Japanese, each a short noun phrase of at most 12 characters.\n"
    "- NEVER copy any text you can read in the image (signs, ship names, shop names, license plates). "
    "Only set text_visible.\n"
    "- Do not guess anyone's identity, nationality or exact location. Generic words only (e.g. 港, 浜辺, 路地).\n"
    "- people = number of people you can see (0 if none).\n"
    "- highlight = how much this shot would make a viewer want to keep watching a travel vlog (5 = best)."
)


def _parse(raw: str) -> dict:
    m = re.search(r"\{.*\}", raw, flags=re.S)
    if not m:
        raise ValueError(f"no JSON in model output: {raw[:200]!r}")
    data = json.loads(m.group(0))
    checks = data.get("checks") or {}
    data["checks"] = {k: bool(checks.get(k)) for k in QUALITY_ITEMS}
    data["quality"] = sum(data["checks"].values())  # computed, not judged by the model
    try:
        data["highlight"] = max(1, min(5, int(data.get("highlight", 3))))
    except (TypeError, ValueError):
        data["highlight"] = 3
    try:
        data["people"] = max(0, int(data.get("people", 0)))
    except (TypeError, ValueError):
        data["people"] = 0
    for k in ("place", "subject", "action", "mood"):
        data[k] = str(data.get(k, "")).strip()[:24]
    data["text_visible"] = bool(data.get("text_visible"))
    return data


def caption_frame(image: Path, model: str | None = None) -> tuple[dict, lmstudio.ChatResult]:
    res = lmstudio.chat([
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": [{"type": "text", "text": "Describe this frame."}, lmstudio.image_part(image)]},
    ], model or config.VISION_MODEL, max_tokens=400)
    return _parse(res.text), res


def caption_clip(clip_dir: Path, recorder=None) -> list[dict]:
    segs = json.loads((clip_dir / "segments.json").read_text(encoding="utf-8"))
    out: list[dict] = []
    for s in segs:
        frame = clip_dir / "frames" / f"S{s['index']:02d}.jpg"
        ctx = recorder.stage("caption", clip_dir.name) if recorder else _null()
        with ctx as m:
            data, res = caption_frame(frame)
            m.update(frames=1, tokens_in=res.prompt_tokens, tokens_out=res.completion_tokens)
        out.append({"shot": f"{clip_dir.name}-S{s['index']:02d}", "start": s["start"], "end": s["end"], **data})
    (clip_dir / "captions.jsonl").write_text(
        "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in out), encoding="utf-8")
    return out


class _null:
    def __enter__(self):
        return {}

    def __exit__(self, *a):
        return False
