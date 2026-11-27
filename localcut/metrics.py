"""Measurement recorder in the spark-vibe bench layout (environment.json / raw.jsonl / summary.json)."""

from __future__ import annotations

import datetime as dt
import json
import platform
import statistics
import time
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path


def _mem_used_mb() -> int | None:
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        st = MEMORYSTATUSEX()
        st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
        return int((st.ullTotalPhys - st.ullAvailPhys) / 1048576)
    except Exception:  # noqa: BLE001 - non-Windows or no ctypes: just skip
        return None


def stats(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    s = sorted(values)
    p95 = s[min(len(s) - 1, int(round(0.95 * (len(s) - 1))))]
    return {"n": len(s), "min": s[0], "median": statistics.median(s), "mean": statistics.fmean(s),
            "p95": p95, "max": s[-1], "stdev": statistics.stdev(s) if len(s) > 1 else 0.0}


class Recorder:
    """Records one JSON line per stage invocation. `out_dir=None` makes it a no-op sink."""

    def __init__(self, out_dir: Path | None, environment: dict | None = None):
        self.out_dir = out_dir
        self.rows: list[dict] = []
        if out_dir:
            out_dir.mkdir(parents=True, exist_ok=True)
            env = {"timestamp": dt.datetime.now().astimezone().isoformat(), "platform": platform.platform(),
                   "machine": platform.machine(), "processor": platform.processor(),
                   "python": platform.python_version(), **(environment or {})}
            (out_dir / "environment.json").write_text(json.dumps(env, ensure_ascii=False, indent=1), encoding="utf-8")
            self._raw = (out_dir / "raw.jsonl").open("a", encoding="utf-8")

    @contextmanager
    def stage(self, name: str, clip_id: str | None = None):
        extra: dict = {}
        t0 = time.perf_counter()
        try:
            yield extra
        finally:
            row = {"stage": name, "clip_id": clip_id, "wall_sec": round(time.perf_counter() - t0, 4),
                   "mem_used_mb": _mem_used_mb(), **extra}
            self.rows.append(row)
            if self.out_dir:
                self._raw.write(json.dumps(row, ensure_ascii=False) + "\n")
                self._raw.flush()

    def summary(self) -> dict:
        by_stage: dict[str, list[dict]] = defaultdict(list)
        for r in self.rows:
            by_stage[r["stage"]].append(r)
        out = {}
        for name, rows in by_stage.items():
            wall = [r["wall_sec"] for r in rows]
            input_sec = sum(r.get("input_sec") or 0 for r in rows)
            frames = sum(r.get("frames") or 0 for r in rows)
            out[name] = {"wall_sec": stats(wall), "total_wall_sec": round(sum(wall), 3),
                         "total_input_sec": round(input_sec, 3), "total_frames": frames,
                         "sec_per_frame": round(sum(wall) / frames, 4) if frames else None}
        mem = [r["mem_used_mb"] for r in self.rows if r.get("mem_used_mb")]
        out["_peak_mem_used_mb"] = max(mem) if mem else None
        return out

    def close(self) -> dict:
        summ = self.summary()
        if self.out_dir:
            self._raw.close()
            (self.out_dir / "summary.json").write_text(json.dumps(summ, ensure_ascii=False, indent=1), encoding="utf-8")
        return summ
