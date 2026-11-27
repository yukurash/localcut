"""`analyze`: the overnight, fully local stage.

footage/*.mp4 -> work/<clip_id>/{probe.json, segments.json, frames/*.jpg, faces.json}
               -> work/clips.json (clip_id <-> local file mapping; never leaves the machine)

Clip IDs (C01, C02, ...) are assigned in file-name order so that nothing derived from the
file name or path has to appear in the text that is later sent to the cloud.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from PIL import Image

from . import config, media
from .metrics import Recorder

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".mkv"}


def list_clips(footage_dir: Path) -> list[Path]:
    return sorted(p for p in footage_dir.iterdir() if p.suffix.lower() in VIDEO_EXTS)


def analyze(footage_dir: Path | None = None, work_dir: Path | None = None, *, faces_enabled: bool = True,
            recorder: Recorder | None = None, log=print) -> dict:
    footage_dir = footage_dir or config.FOOTAGE_DIR
    work_dir = work_dir or config.WORK_DIR
    work_dir.mkdir(parents=True, exist_ok=True)
    rec = recorder or Recorder(None)
    clips = list_clips(footage_dir)
    mapping = {}
    detect = None
    if faces_enabled:
        try:
            from . import faces as _faces
            _faces._session()
            detect = _faces
        except (FileNotFoundError, ImportError) as e:
            log(f"[faces] disabled: {e}")

    for n, path in enumerate(clips, start=1):
        clip_id = f"C{n:02d}"
        cdir = work_dir / clip_id
        cdir.mkdir(exist_ok=True)
        mapping[clip_id] = str(path)

        with rec.stage("probe", clip_id) as m:
            pr = media.probe(path)
            m.update(input_sec=pr.duration, input_bytes=pr.size_bytes)
        (cdir / "probe.json").write_text(json.dumps(pr.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")

        with rec.stage("scene", clip_id) as m:
            cuts = media.scene_changes(path)
            segs = media.segments(pr.duration, cuts)
            m.update(input_sec=pr.duration, cuts=len(cuts), frames=len(segs))
        (cdir / "segments.json").write_text(
            json.dumps([{"index": s.index, "start": s.start, "end": s.end, "mid": round(s.mid, 3)} for s in segs],
                       indent=1), encoding="utf-8")

        with rec.stage("keyframes", clip_id) as m:
            frames = [media.extract_frame(path, s.mid, cdir / "frames" / f"S{s.index:02d}.jpg") for s in segs]
            m.update(frames=len(frames), output_bytes=sum(f.stat().st_size for f in frames))

        if detect:
            with rec.stage("faces", clip_id) as m:
                face_log = {}
                for f in frames:
                    img = Image.open(f)
                    found = detect.detect(img)
                    face_log[f.stem] = [vars(x) for x in found]
                    if found:
                        detect.blur(img, found).save(cdir / "frames" / f"{f.stem}.blur.jpg", quality=90)
                m.update(frames=len(frames), faces=sum(len(v) for v in face_log.values()))
            (cdir / "faces.json").write_text(json.dumps(face_log, indent=1), encoding="utf-8")

        log(f"{clip_id}: {pr.duration:5.1f}s {pr.width}x{pr.height} cuts={len(cuts)} frames={len(segs)}")

    (work_dir / "clips.json").write_text(json.dumps(mapping, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"clips": len(clips), "work_dir": str(work_dir), "finished_at": time.time()}
