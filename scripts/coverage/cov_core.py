#!/usr/bin/env python3
"""Shared helpers for the T-COVERAGE-FULL pipeline (session 6ddde224).

Everything in here is deliberately small and dependency-free (standard library only) so the
same code runs in this sandbox and on a hosted runner:

* ``fetch``/``fetch_json`` record HTTP status, byte count, final URL and errors for evidence.
* ``canon_team`` normalises team labels for strict joining (no fuzzy matching is ever published).
* ``devig_proportional`` converts a two-sided decimal price into no-vig probabilities.
* ``json_dump`` writes stable, diff-friendly JSON.

No value produced here is a probability unless it comes from a source price (``devig_*``) or from
the explicitly labelled models in ``build_coverage.py``.
"""
from __future__ import annotations

import json
import re
import ssl
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

UA = "Mozilla/5.0 (compatible; MaltaProj2-coverage/1.0; +https://github.com/buffedlizard55-lab/MaltaProj2)"
UA_BROWSER = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0 Safari/537.36")
MAX_BYTES = 8_000_000


# --------------------------------------------------------------------------------------- time
def now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def now_iso() -> str:
    return now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_ms(value: Any) -> datetime | None:
    """HotSpawn publishes epoch milliseconds; accept ISO strings as well."""
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)) or (isinstance(value, str) and re.fullmatch(r"\d{9,13}", value)):
            num = float(value)
            if num > 1e11:  # milliseconds
                num /= 1000.0
            return datetime.fromtimestamp(num, tz=timezone.utc)
        if isinstance(value, str):
            return parse_any(value)
    except (ValueError, OverflowError, OSError):
        return None
    return None


def parse_any(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    text = re.sub(r"\.(\d{3})\d*", r".\1", text)
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S%z", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def to_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def hours_since(dt: datetime | None) -> float | None:
    if dt is None:
        return None
    return (now_utc() - dt.astimezone(timezone.utc)).total_seconds() / 3600.0


# --------------------------------------------------------------------------------------- http
def fetch(url: str, headers: dict[str, str] | None = None, timeout: int = 45) -> dict:
    """GET a URL and return a dict with the body plus the metadata needed as evidence."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    result: dict[str, Any] = {"url": url, "status": None, "bytes": 0, "body": b"",
                              "error": None, "final_url": None, "content_type": None,
                              "fetched_at_utc": now_iso()}
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as resp:
            body = resp.read(MAX_BYTES)
            result.update(status=resp.status, bytes=len(body), body=body, final_url=resp.geturl(),
                          content_type=resp.headers.get("Content-Type"))
    except urllib.error.HTTPError as exc:  # HTTP error still carries a body worth recording
        body = b""
        try:
            body = exc.read(MAX_BYTES)
        except Exception:  # noqa: BLE001
            pass
        result.update(status=exc.code, bytes=len(body), body=body, error=f"HTTPError {exc.code}",
                      final_url=getattr(exc, "url", url),
                      content_type=exc.headers.get("Content-Type") if exc.headers else None)
    except Exception as exc:  # noqa: BLE001  (network/DNS/TLS)
        result.update(error=f"{type(exc).__name__}: {exc}")
    return result


def fetch_json(url: str, headers: dict[str, str] | None = None, timeout: int = 45) -> tuple[Any, dict]:
    res = fetch(url, {"Accept": "application/json", **(headers or {})}, timeout=timeout)
    data = None
    if res["body"]:
        try:
            data = json.loads(res["body"].decode("utf-8", "replace"))
        except json.JSONDecodeError as exc:
            res["error"] = f"JSONDecodeError: {exc}"
    meta = {k: v for k, v in res.items() if k not in ("body",)}
    return data, meta


def save_sample(sample_dir: Path | None, name: str, payload: Any, limit: int = 300_000) -> str | None:
    """Store a bounded verbatim sample as inert evidence (never as a published page)."""
    if sample_dir is None:
        return None
    sample_dir.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, (bytes, bytearray)):
        text = bytes(payload[:limit]).decode("utf-8", "replace")
    elif isinstance(payload, str):
        text = payload[:limit]
    else:
        text = json.dumps(payload, indent=1, ensure_ascii=False)[:limit]
    target = sample_dir / name
    target.write_text(text, encoding="utf-8")
    return name


# ----------------------------------------------------------------------------------- team names
_PUNCT_RE = re.compile(r"[^0-9a-z ]+")
_WS_RE = re.compile(r"\s+")
LEADING = ("team ", "the ")
TRAILING = (" esports", " esport", " gaming", " team")


def canon_team(name: Any) -> str:
    """Normalise a team label for strict comparison.

    Only whitespace, case, accents and punctuation are normalised, plus the documented
    leading/trailing filler words below ("team"/"the" in front; "esports"/"esport"/"gaming"/"team"
    behind). Anything else (for example "Academy", "Prospects", "Ares") is significant and is never
    removed, so two different teams can never collapse.
    """
    if name is None:
        return ""
    text = unicodedata.normalize("NFKD", str(name))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold().strip()
    text = text.replace("&", " and ")
    text = _PUNCT_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    for prefix in LEADING:
        if text.startswith(prefix) and len(text) > len(prefix) + 1:
            text = text[len(prefix):]
    for suffix in TRAILING:
        if text.endswith(suffix) and len(text) > len(suffix) + 1:
            text = text[: -len(suffix)]
    return text.strip()


def same_teams(fixture_pair: tuple[str, str], source_pair: tuple[str, str]) -> bool:
    """True when both sides match exactly after canonicalisation (either orientation)."""
    a1, b1 = canon_team(fixture_pair[0]), canon_team(fixture_pair[1])
    a2, b2 = canon_team(source_pair[0]), canon_team(source_pair[1])
    return (a1, b1) == (a2, b2) or (a1, b1) == (b2, a2)


# --------------------------------------------------------------------------------------- odds
def devig_proportional(dec_a: float, dec_b: float) -> tuple[float, float, float]:
    """Two-way decimal prices -> proportional no-vig probabilities.

    Returns (p_a, p_b, overround). ``overround = 1/dec_a + 1/dec_b``; each raw implied
    probability is divided by the overround. Raises ValueError on nonsense input so a bad price
    can never silently become a published probability.
    """
    if not (dec_a and dec_b) or dec_a <= 1.0 or dec_b <= 1.0:
        raise ValueError(f"decimal prices must be > 1.0 (got {dec_a!r}, {dec_b!r})")
    raw_a, raw_b = 1.0 / dec_a, 1.0 / dec_b
    overround = raw_a + raw_b
    if overround <= 0:
        raise ValueError("invalid overround")
    return raw_a / overround, raw_b / overround, overround


def american_to_decimal(price: Any) -> float | None:
    try:
        num = float(price)
    except (TypeError, ValueError):
        return None
    if num == 0:
        return None
    return 1.0 + (num / 100.0 if num > 0 else 100.0 / abs(num))


# --------------------------------------------------------------------------------------- io
def json_dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False, sort_keys=False) + "\n",
                    encoding="utf-8")


def sleep(seconds: float) -> None:
    time.sleep(seconds)
