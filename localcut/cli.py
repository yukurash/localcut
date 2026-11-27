"""Command line entry point: python -m localcut <command>."""

from __future__ import annotations

import argparse
import platform
import subprocess
import sys

from . import config


def _ok(label: str, good: bool, detail: str = "") -> bool:
    print(f"[{'OK' if good else 'NG'}] {label}{(' - ' + detail) if detail else ''}")
    return good


def doctor(_args) -> int:
    """Check that every local dependency is reachable. Network calls go to localhost only."""
    results = [_ok("python", True, f"{platform.python_version()} {platform.machine()}")]
    for tool in ("ffmpeg", "ffprobe", "whisper-cli"):
        path = config.find_tool(tool)
        detail = path or "not found (PATH or LOCALCUT_TOOLS_DIR)"
        if path and tool == "ffmpeg":
            first = subprocess.run([path, "-hide_banner", "-version"], capture_output=True, text=True).stdout
            detail = first.splitlines()[0] if first else path
        results.append(_ok(tool, path is not None, detail))
    try:
        from . import lmstudio
        models = lmstudio.list_models()
        results.append(_ok("LM Studio API", True, config.LMSTUDIO_URL))
        for m in (config.VISION_MODEL, config.CHAT_MODEL):
            results.append(_ok(f"model {m}", m in models, "loaded/available" if m in models else "missing"))
    except Exception as e:  # noqa: BLE001 - doctor reports, never raises
        results.append(_ok("LM Studio API", False, f"{config.LMSTUDIO_URL} ({type(e).__name__})"))
    for label, d in (("footage dir", config.FOOTAGE_DIR), ("work dir", config.WORK_DIR)):
        inside_repo = config.REPO_ROOT in d.parents or d == config.REPO_ROOT
        results.append(_ok(label, not inside_repo, f"{d}{' (inside the repo!)' if inside_repo else ''}"))
    return 0 if all(results) else 1


def _run_dir(name: str):
    import datetime as dt

    return config.RUNS_DIR / f"{dt.datetime.now():%Y%m%d-%H%M%S}-{name}"


def analyze_cmd(args) -> int:
    from .analyze import analyze
    from .metrics import Recorder

    rec = Recorder(_run_dir("analyze"), {"command": "analyze"})
    result = analyze(faces_enabled=not args.no_faces, recorder=rec)
    summary = rec.close()
    for stage, s in summary.items():
        if not stage.startswith("_"):
            print(f"{stage:10s} total {s['total_wall_sec']:8.2f}s  frames {s['total_frames']}")
    print(f"peak memory used: {summary['_peak_mem_used_mb']} MB / clips: {result['clips']}")
    return 0


def caption_cmd(args) -> int:
    from .caption import caption_clip
    from .metrics import Recorder

    rec = Recorder(_run_dir("caption"), {"command": "caption", "vision_model": config.VISION_MODEL})
    for cdir in sorted(p for p in config.WORK_DIR.iterdir() if p.is_dir() and p.name.startswith("C")):
        if args.only and cdir.name not in args.only:
            continue
        caps = caption_clip(cdir, recorder=rec)
        for c in caps:
            print(f"{c['shot']} {c['place']} / {c['subject']} / {c['action']} people={c['people']} "
                  f"★{c['highlight']} q={c['quality']}")
    s = rec.close().get("caption", {})
    print(f"caption: {s.get('total_frames')} frames, {s.get('sec_per_frame')} s/frame")
    return 0


def brief_cmd(args) -> int:
    from .brief import build_brief, load_shots

    text = build_brief(load_shots(), detail=args.detail)
    print(text)
    print(f"# {len(text.encode('utf-8'))} bytes")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="localcut", description="Footage stays home. Words go to the cloud.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor", help="check local dependencies").set_defaults(func=doctor)
    a = sub.add_parser("analyze", help="overnight local analysis of the footage folder")
    a.add_argument("--no-faces", action="store_true", help="skip face detection/blur")
    a.set_defaults(func=analyze_cmd)
    c = sub.add_parser("caption", help="local VLM captions for every keyframe")
    c.add_argument("--only", nargs="*", help="clip ids, e.g. C01 C04")
    c.set_defaults(func=caption_cmd)
    b = sub.add_parser("brief", help="print the edit brief (what the cloud would receive, before the gate)")
    b.add_argument("--detail", default="normal", choices=["normal", "full"])
    b.set_defaults(func=brief_cmd)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
