"""Runtime configuration (environment variables only; nothing is read from the repo)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def _path(name: str, default: Path) -> Path:
    return Path(os.environ.get(name, str(default))).expanduser().resolve()


REPO_ROOT = Path(__file__).resolve().parents[1]

# Footage and work files live OUTSIDE the repo by default (sibling "<repo>-private" folder).
PRIVATE_ROOT = _path("LOCALCUT_PRIVATE_DIR", REPO_ROOT.parent / f"{REPO_ROOT.name}-private")
FOOTAGE_DIR = _path("LOCALCUT_FOOTAGE_DIR", PRIVATE_ROOT / "footage")
WORK_DIR = _path("LOCALCUT_WORK_DIR", PRIVATE_ROOT / "work")
RUNS_DIR = _path("LOCALCUT_RUNS_DIR", PRIVATE_ROOT / "runs")
TOOLS_DIR = _path("LOCALCUT_TOOLS_DIR", PRIVATE_ROOT / "tools")

# Same variable names as the official spark-vibe kit, so one LM Studio setup serves both.
LMSTUDIO_URL = os.environ.get("SPARK_LMSTUDIO_URL", "http://localhost:1234/v1")
CHAT_MODEL = os.environ.get("SPARK_CHAT_MODEL", "qwen/qwen3.5-9b")
VISION_MODEL = os.environ.get("SPARK_VISION_MODEL", "google/gemma-4-e4b")
REASONING_EFFORT = os.environ.get("SPARK_REASONING_EFFORT", "none")


def find_tool(name: str) -> str | None:
    """Locate an executable on PATH or under TOOLS_DIR (e.g. tools/ffmpeg/bin/ffmpeg.exe)."""
    found = shutil.which(name)
    if found:
        return found
    exe = name if name.lower().endswith(".exe") else f"{name}.exe"
    for p in TOOLS_DIR.rglob(exe) if TOOLS_DIR.is_dir() else []:
        return str(p)
    return None
