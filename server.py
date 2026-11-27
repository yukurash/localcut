"""localcut MCP server (stdio).

Footage stays home, words go to the cloud: every tool result passes through the egress gate,
so the cloud model only ever receives short, masked, logged text. Works with Claude Code
(.mcp.json in this repo) and GitHub Copilot CLI / VS Code (same command line).
Structure follows the spark-vibe kit's server.py (mcp>=2.3 MCPServer).
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.mcpserver import MCPServer  # noqa: E402

from localcut import brief, config, gate, plan as planmod  # noqa: E402

mcp = MCPServer("localcut")


def _out(tool: str, payload, budget_bytes: int = 4000) -> str:
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, indent=1)
    try:
        rel = gate.release(text, tool=tool, budget_bytes=budget_bytes)
    except gate.GateRefused as e:
        return json.dumps({"error": "egress_refused", "detail": str(e)})
    return rel.text


def _plans_dir() -> Path:
    d = config.WORK_DIR / "plans"
    d.mkdir(parents=True, exist_ok=True)
    return d


@mcp.tool()
def footage_status() -> str:
    """Numbers only: how many clips, total duration, size of the raw footage, and analysis progress.
    Raw footage never leaves this machine; this tool tells you how much stays home."""
    clips_file = config.WORK_DIR / "clips.json"
    if not clips_file.is_file():
        return _out("footage_status", {"analyzed": False, "hint": "run `python -m localcut analyze` locally first"})
    clips = json.loads(clips_file.read_text(encoding="utf-8"))
    total_sec = total_bytes = 0.0
    captioned = 0
    for cid in clips:
        probe = json.loads((config.WORK_DIR / cid / "probe.json").read_text(encoding="utf-8"))
        total_sec += probe["duration"]
        total_bytes += probe["size_bytes"]
        captioned += (config.WORK_DIR / cid / "captions.jsonl").is_file()
    return _out("footage_status", {"clips": len(clips), "captioned_clips": captioned,
                                   "total_sec": round(total_sec, 1), "raw_bytes_kept_local": int(total_bytes)})


@mcp.tool()
def get_edit_brief(budget_bytes: int = 12000) -> str:
    """The edit brief: one line per shot (place, subject/action, mood, people count, highlight, quality),
    produced on this machine by a local VLM. This text is the ONLY footage-derived content you receive.
    Use the shot ids (e.g. C03-S02) and in/out seconds when you write the edit plan."""
    shots = brief.load_shots()
    if not shots:
        return _out("get_edit_brief", {"error": "no captions yet; run `python -m localcut caption` locally"})
    return _out("get_edit_brief", brief.build_brief(shots), budget_bytes=min(int(budget_bytes), 20000))


@mcp.tool()
def submit_edit_plan(plan_json: str) -> str:
    """Validate an edit plan locally and store it. plan_json:
    {"title": str (<=40 chars), "target_sec": number,
     "cuts": [{"shot": "C01-S00", "in": seconds, "out": seconds, "telop": str (<=18 chars, may be "")}],
     "thumbnail": {"shot": "C09-S03"}}
    in/out are seconds within the clip (see the shot's range in the brief). Returns plan_id or problems."""
    p, problems = planmod.validate(plan_json, brief.load_shots())
    if p is None or problems:
        return _out("submit_edit_plan", {"ok": False, "problems": problems})
    plan_id = f"P{dt.datetime.now():%m%d%H%M%S}"
    (_plans_dir() / f"{plan_id}.json").write_text(plan_json if isinstance(plan_json, str) else json.dumps(plan_json),
                                                  encoding="utf-8")
    return _out("submit_edit_plan", {"ok": True, "plan_id": plan_id, "cuts": len(p.cuts),
                                     "duration_sec": round(p.duration, 1)})


def _load_plan(plan_id: str) -> planmod.Plan:
    raw = (_plans_dir() / f"{plan_id}.json").read_text(encoding="utf-8")
    p, problems = planmod.validate(raw, brief.load_shots())
    if p is None:
        raise ValueError("; ".join(problems))
    return p


@mcp.tool()
def render_preview(plan_id: str, quality: str = "draft") -> str:
    """Render the plan locally to a vertical 1080x1920 MP4 (faces blurred, telops burned in).
    Takes roughly 2-3x the video length on a laptop CPU. Returns ids and numbers only, never paths."""
    from localcut import render

    p = _load_plan(plan_id)
    render_id = f"{plan_id}-{quality}"
    info = render.render(p, render_id, quality=quality)
    return _out("render_preview", info)


@mcp.tool()
def review_render(render_id: str) -> str:
    """Local VLM checks one frame per cut of the rendered video (telop inside the frame and readable,
    no recognizable faces, not black/white). Returns pass/fail booleans only."""
    from localcut import review

    plan_id = render_id.rsplit("-", 1)[0]
    return _out("review_render", review.review(_load_plan(plan_id), render_id))


@mcp.tool()
def egress_report() -> str:
    """How many bytes this server has returned to the cloud so far, per tool, and what was masked."""
    return _out("egress_report", gate.report())


if __name__ == "__main__":
    mcp.run()
