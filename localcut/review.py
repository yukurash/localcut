"""Local QA of a rendered cut, in the spark-vibe `visual_review` checklist style.

The local VLM looks at frames of the final video. Only booleans leave this module:
the model's free-text observations stay in work/renders/<id>/review.json.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from . import config, lmstudio, media
from .plan import Plan

SYSTEM = (
    "You verify one frame of a vertical travel video against acceptance criteria. For each criterion, first "
    "describe what you see, then decide met true/false based ONLY on that observation. Reply with ONLY JSON: "
    '{"criteria":[{"criterion":string,"observed":string,"met":true|false}]}'
)


def criteria_for(telop: str, extra: str = "") -> list[str]:
    items = []
    if telop:
        items.append(f"The caption text '{telop}' is fully inside the frame (not cut off) and readable.")
    items += [
        "No person's face is clearly recognizable: faces are blurred, too small, or there are no people.",
        "The frame is not almost black and not blown out to white.",
    ]
    if extra:
        items.append(extra)
    return items


def review(plan: Plan, render_id: str) -> dict:
    out_dir = config.WORK_DIR / "renders" / render_id
    final = out_dir / "final.mp4"
    ff = media._tool("ffmpeg")
    results, t = [], 0.0
    for i, c in enumerate(plan.cuts):
        frame = out_dir / f"review_{i:03d}.jpg"
        subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t + c.length / 2:.2f}", "-i", str(final),
                        "-frames:v", "1", "-vf", "scale=540:-2", str(frame)], check=True)
        crit = criteria_for(c.telop)
        res = lmstudio.chat([
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": [{"type": "text", "text": "Criteria:\n- " + "\n- ".join(crit)},
                                         lmstudio.image_part(frame)]},
        ], config.VISION_MODEL, max_tokens=700)
        m = re.search(r"\{.*\}", res.text, flags=re.S)
        try:
            items = json.loads(m.group(0)).get("criteria", []) if m else []
        except json.JSONDecodeError:
            items = []
        met = [bool(x.get("met")) for x in items if isinstance(x, dict)][: len(crit)]
        results.append({"cut": i, "shot": c.shot, "met": met, "n": len(crit), "observed": items})
        t += c.length
    (out_dir / "review.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    passed = sum(1 for r in results if r["met"] and all(r["met"]) and len(r["met"]) == r["n"])
    # Only booleans are returned; free-text observations stay local.
    return {"render_id": render_id, "cuts": len(results), "cuts_passed": passed,
            "verdict": "pass" if passed == len(results) else "fail",
            "failed": [{"cut": r["cut"], "shot": r["shot"], "met": r["met"]} for r in results
                       if not (r["met"] and all(r["met"]) and len(r["met"]) == r["n"])]}
