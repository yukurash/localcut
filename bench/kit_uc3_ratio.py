"""Run the spark-vibe kit's UC3 `visual_review` on this machine with the kit's own images and prompts,
and compare the latency with the kit's published Surface Laptop Ultra (RTX Spark) results.

    python bench/kit_uc3_ratio.py --kit <path to a clone of the kit> --n 5 --arms checklist holistic

The kit's functions are called directly (same code, same images, same model id), so the only thing
that differs from the published run is the hardware. The ratio local/Ultra is used to estimate how
localcut's caption stage would run on the Ultra. It is an estimate: prompts and image sizes differ.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from localcut.metrics import stats  # noqa: E402

VARIANTS = ["pass_original", "pass_other_values", "fail_stacked", "fail_two_cards", "fail_red_button",
            "fail_wrong_title", "fail_light_theme"]
LABEL = {v: ("pass" if v.startswith("pass") else "fail") for v in VARIANTS}


def load_kit(kit: Path):
    spec = importlib.util.spec_from_file_location("spark_vibe_server", kit / "server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kit", type=Path, required=True)
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--arms", nargs="+", default=["checklist", "holistic"])
    ap.add_argument("--out", type=Path, default=Path("bench/results") / f"kit-uc3-{dt.datetime.now():%Y%m%d-%H%M}")
    args = ap.parse_args()

    kit = load_kit(args.kit)
    published = json.loads((args.kit / "bench/results/uc3/summary.json").read_text(encoding="utf-8"))
    published_env = json.loads((args.kit / "bench/results/uc3/environment.json").read_text(encoding="utf-8"))
    expectation = published["expectation"]
    shots = args.kit / "docs/media/uc3-variants"
    args.out.mkdir(parents=True, exist_ok=True)
    lms = Path.home() / ".lmstudio/bin/lms.exe"
    env = {"captured_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
           "platform": platform.platform(), "machine": platform.machine(), "processor": platform.processor(),
           "python": platform.python_version(), "vision_model": kit.VISION_MODEL,
           "lms_ps": subprocess.run([str(lms), "ps"], capture_output=True, text=True).stdout if lms.exists() else None}
    (args.out / "environment.json").write_text(json.dumps(env, ensure_ascii=False, indent=1), encoding="utf-8")

    kit.visual_review(str(shots / "pass_original.png"), expectation)  # warm-up, as in the kit
    summary = {"n_per_item": args.n, "arms": {}, "published_ultra": {}, "published_env": published_env.get("gpu")}
    with (args.out / "raw.jsonl").open("w", encoding="utf-8") as raw:
        for arm in args.arms:
            lat, correct = [], 0
            for v in VARIANTS:
                for i in range(args.n):
                    t0 = time.perf_counter()
                    out = kit.visual_review(str(shots / f"{v}.png"), expectation, mode=arm)
                    sec = time.perf_counter() - t0
                    try:
                        verdict = str(json.loads(out).get("verdict", "unparseable")).lower()
                    except json.JSONDecodeError:
                        verdict = "unparseable"
                    correct += verdict == LABEL[v]
                    lat.append(sec)
                    raw.write(json.dumps({"arm": arm, "variant": v, "run": i, "label": LABEL[v], "verdict": verdict,
                                          "latency_sec": round(sec, 3), "output": out}, ensure_ascii=False) + "\n")
                    raw.flush()
                    print(f"{arm:10s} {v:18s} #{i} {sec:6.1f}s {verdict}", flush=True)
            pub = published["visual_review"][arm]
            summary["arms"][arm] = {"latency_sec": stats(lat), "accuracy": round(correct / len(lat), 3)}
            summary["published_ultra"][arm] = {"latency_sec": pub["latency_sec"], "accuracy": pub["confusion"]["accuracy"]}
            summary["arms"][arm]["ratio_local_over_ultra_median"] = round(
                summary["arms"][arm]["latency_sec"]["median"] / pub["latency_sec"]["median"], 2)
    (args.out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({a: (s["latency_sec"]["median"], s["ratio_local_over_ultra_median"], s["accuracy"])
                      for a, s in summary["arms"].items()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
