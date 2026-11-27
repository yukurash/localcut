import pytest

from localcut import config, gate


@pytest.fixture(autouse=True)
def runs_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path)
    return tmp_path


@pytest.mark.parametrize("text,kind", [
    ("連絡先 090-1234-5678 まで", "phone"),
    ("mail: taro.yamada@example.com", "email"),
    ("〒900-0001 に送って", "postal_code"),
    ("沖縄県那覇市泉崎1丁目2番", "address"),
    ("品川 300 さ 12-34 の車", "plate"),
    ("C:\\Users\\me\\footage\\C01_pexels_123.mp4 を見て", "windows_path"),
    ("IMG_0042.MOV と", "media_file"),
    ("26.2124, 127.6809 付近", "gps"),
    ("撮影 2026-11-27 14:03:22", "clock_time"),
    ("https://example.com/a", "url"),
])
def test_mask_patterns(text, kind):
    masked, counts = gate.mask(text)
    assert counts.get(kind, 0) >= 1, (masked, counts)
    assert f"[MASK:{kind}]" in masked


def test_brief_line_is_untouched():
    line = "C01-S00 | 0.0-6.5 | 港 | 旅客船 / 接岸 | 晴れ | 7 | ★★★★ | 4/4"
    masked, counts = gate.mask(line)
    assert masked == line and counts == {}


def test_release_logs_full_text_and_bytes(runs_tmp):
    rel = gate.release("夕日の浜辺 090-1111-2222", tool="get_edit_brief", use_llm=False)
    assert "[MASK:phone]" in rel.text
    assert rel.bytes == len(rel.text.encode("utf-8"))
    saved = list((runs_tmp / "egress").glob("*.txt"))
    assert len(saved) == 1 and saved[0].read_text(encoding="utf-8") == rel.text
    rep = gate.report()
    assert rep["bytes_sent"] == rel.bytes and rep["masks"] == {"phone": 1}


def test_release_fails_closed_over_budget(runs_tmp):
    with pytest.raises(gate.GateRefused):
        gate.release("あ" * 5000, tool="get_edit_brief", budget_bytes=1000, use_llm=False)
    rep = gate.report()
    assert rep["refused"] == 1 and rep["bytes_sent"] == 0
    assert not list((runs_tmp / "egress").glob("*.txt"))
