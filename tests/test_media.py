import numpy as np

from localcut import faces
from localcut.media import segments


def test_segments_no_cuts_splits_long_clip():
    segs = segments(20.0, [], max_len=8.0)
    assert len(segs) == 3
    assert segs[0].start == 0.0 and segs[-1].end == 20.0


def test_segments_drops_cuts_too_close():
    segs = segments(10.0, [0.5, 3.0, 3.4, 9.6], min_len=1.5)
    assert [s.start for s in segs] == [0.0, 3.0]


def test_segments_caps_count():
    cuts = [i * 2.0 for i in range(1, 30)]
    segs = segments(60.0, cuts, max_segments=12)
    assert len(segs) == 12
    assert segs[0].start == 0.0 and segs[-1].end == 60.0
    assert all(a.end == b.start for a, b in zip(segs, segs[1:]))


def test_yunet_decode_single_anchor():
    outputs = {}
    for s in faces.STRIDES:
        n = (faces.INPUT // s) ** 2
        outputs[f"cls_{s}"] = np.zeros((1, n, 1), np.float32)
        outputs[f"obj_{s}"] = np.zeros((1, n, 1), np.float32)
        outputs[f"bbox_{s}"] = np.zeros((1, n, 4), np.float32)
    # one confident anchor at stride 32, row 2, col 3 -> centre (3*32, 2*32), size exp(0)*32
    idx = 2 * (faces.INPUT // 32) + 3
    outputs["cls_32"][0, idx, 0] = 0.9
    outputs["obj_32"][0, idx, 0] = 0.9
    found = faces.decode(outputs)
    assert len(found) == 1
    f = found[0]
    assert abs(f.x - (96 - 16)) < 1e-3 and abs(f.y - (64 - 16)) < 1e-3
    assert abs(f.w - 32) < 1e-3 and abs(f.score - 0.9) < 1e-3


def test_nms_removes_overlap():
    a = faces.Face(0, 0, 10, 10, 0.9)
    b = faces.Face(1, 1, 10, 10, 0.8)
    c = faces.Face(50, 50, 10, 10, 0.7)
    assert faces.nms([a, b, c]) == [a, c]
