from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

UNKNOWN = "unknown"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def fold(value: Any) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text)
    return "".join(char for char in text if not unicodedata.combining(char)).casefold().strip()


def slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", fold(value)).strip("-")
    return cleaned or "run"


def clean_text(value: Any, max_length: int = 10_000) -> str:
    if value is None:
        return UNKNOWN
    if isinstance(value, bool):
        return "true" if value else "false"
    text = re.sub(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f]", " ", str(value))
    text = re.sub(r"\s+", " ", text).strip()
    return (text[:max_length] if text else UNKNOWN)


SECRET_PATTERNS = [
    re.compile(r"(?i)\b(api[_ -]?key|token|secret|password|senha)\b\s*[:=]\s*\S+"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
]


def redact(value: Any, max_length: int = 700) -> str:
    text = clean_text(value, max_length=max_length)
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


INJECTION_PATTERNS = [
    "ignore previous",
    "ignore all previous",
    "system prompt",
    "developer message",
    "execute this command",
    "desconsidere as instrucoes",
    "ignore as instrucoes",
]


def has_injection_signal(value: Any) -> bool:
    lowered = fold(value)
    return any(pattern in lowered for pattern in INJECTION_PATTERNS)


def stable_hash(value: Any, length: int = 12) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_datetime(value: Any) -> datetime | None:
    text = clean_text(value)
    if text == UNKNOWN:
        return None
    variants = [text, text.replace("Z", "+00:00")]
    for variant in variants:
        try:
            parsed = datetime.fromisoformat(variant)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            pass
    for pattern in ("%d/%m/%Y", "%d/%m/%Y %H:%M", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, pattern).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def percent(numerator: int | float, denominator: int | float) -> float | None:
    if not denominator:
        return None
    return round(float(numerator) / float(denominator) * 100, 1)


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]

