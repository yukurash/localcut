"""Egress gate: everything an MCP tool returns passes through here before it reaches the cloud model.

What the gate does
- masks patterns that should never leave (phone, e-mail, postal code, addresses, plates, URLs,
  local paths / media file names, GPS-like coordinates, wall-clock timestamps)
- optional second pass: the LOCAL LLM lists names of people / shops / specific places, which are masked
- refuses (fails closed) when the text is over the byte budget
- logs every release: egress.jsonl (bytes, sha256, mask counts) + the full released text

What the gate is NOT: a sandbox. It controls what this MCP server returns. It cannot stop a client
that reads files by other means; pair it with client-side deny rules (see .claude/settings.json).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import config

PATTERNS: list[tuple[str, re.Pattern]] = [
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("url", re.compile(r"https?://\S+|www\.\S+")),
    ("windows_path", re.compile(r"[A-Za-z]:[\\/][^\s|]+")),
    ("media_file", re.compile(r"[\w\-]+\.(?:mp4|mov|m4v|mkv|jpg|jpeg|png|heic|wav|m4a)\b", re.I)),
    ("phone", re.compile(r"(?<!\d)0\d{1,4}[-‐ー\s]?\d{1,4}[-‐ー\s]?\d{3,4}(?!\d)")),
    ("postal_code", re.compile(r"〒?\s?(?<!\d)\d{3}-\d{4}(?!\d)")),
    ("address", re.compile(r"(?:東京都|北海道|(?:京都|大阪)府|.{2,3}県).{1,6}?[市区町村郡].{0,12}?(?:\d+丁目|\d+番地?|\d+-\d+)")),
    ("plate", re.compile(r"[一-龥]{1,4}\s?\d{2,3}\s?[ぁ-ん]\s?\d{1,2}-?\d{2}")),
    ("gps", re.compile(r"[-+]?\d{1,3}\.\d{4,}\s*,\s*[-+]?\d{1,3}\.\d{4,}")),
    ("clock_time", re.compile(r"(?<!\d)\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?")),
]


class GateRefused(RuntimeError):
    pass


@dataclass
class Release:
    text: str
    bytes: int
    sha256: str
    masks: dict[str, int] = field(default_factory=dict)
    llm_masks: list[str] = field(default_factory=list)


def mask(text: str) -> tuple[str, dict[str, int]]:
    counts: dict[str, int] = {}
    for name, pat in PATTERNS:
        text, n = pat.subn(f"[MASK:{name}]", text)
        if n:
            counts[name] = n
    return text, counts


def llm_names(text: str) -> list[str]:
    """Second pass with the LOCAL model: proper nouns that identify people, shops or exact places."""
    from . import lmstudio

    res = lmstudio.chat([
        {"role": "system", "content": "List proper nouns in the text that name a specific person, shop, company, "
         "ship, hotel or exact address. Generic words (港, 浜辺, 屋台, 夕日) are NOT proper nouns. "
         'Reply with ONLY JSON: {"names": [string]}'},
        {"role": "user", "content": text},
    ], os.environ.get("LOCALCUT_GATE_MODEL", config.VISION_MODEL), max_tokens=300)
    m = re.search(r"\{.*\}", res.text, flags=re.S)
    try:
        names = json.loads(m.group(0)).get("names", []) if m else []
    except json.JSONDecodeError:
        names = []
    return [n for n in names if isinstance(n, str) and len(n.strip()) >= 2 and n in text]


def _log_dir() -> Path:
    d = config.RUNS_DIR / "egress"
    d.mkdir(parents=True, exist_ok=True)
    return d


def release(text: str, tool: str, budget_bytes: int = 12000, use_llm: bool | None = None) -> Release:
    masked, counts = mask(text)
    llm_found: list[str] = []
    if use_llm is None:
        use_llm = os.environ.get("LOCALCUT_GATE_LLM", "0") == "1"
    if use_llm:
        for name in sorted(set(llm_names(masked)), key=len, reverse=True):
            masked = masked.replace(name, "[MASK:name]")
            llm_found.append(name)
        if llm_found:
            counts["name"] = counts.get("name", 0) + len(llm_found)
    data = masked.encode("utf-8")
    if len(data) > budget_bytes:
        _write_log({"tool": tool, "bytes": len(data), "refused": True, "budget": budget_bytes})
        raise GateRefused(f"{len(data)} bytes exceeds the egress budget of {budget_bytes} bytes; nothing was sent")
    sha = hashlib.sha256(data).hexdigest()
    (_log_dir() / f"{sha[:16]}.txt").write_bytes(data)
    _write_log({"tool": tool, "bytes": len(data), "sha256": sha, "masks": counts, "llm_masks": len(llm_found)})
    return Release(masked, len(data), sha, counts, llm_found)


def _write_log(row: dict) -> None:
    row = {"ts": dt.datetime.now().astimezone().isoformat(timespec="seconds"), **row}
    with (config.RUNS_DIR / "egress.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def report() -> dict:
    path = config.RUNS_DIR / "egress.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.is_file() else []
    sent = [r for r in rows if not r.get("refused")]
    masks: dict[str, int] = {}
    for r in sent:
        for k, v in (r.get("masks") or {}).items():
            masks[k] = masks.get(k, 0) + v
    return {"releases": len(sent), "refused": len(rows) - len(sent), "bytes_sent": sum(r["bytes"] for r in sent),
            "masks": masks, "by_tool": {t: sum(r["bytes"] for r in sent if r["tool"] == t)
                                        for t in sorted({r["tool"] for r in sent})}}
