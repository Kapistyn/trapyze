"""Web-service settings for the shared API gateway (tz.api in the helper).

A connection can carry an "api" block: where the service lives, where the key
goes and the shared limits. The limits below are the free plans' as published
in November 2026; people on a paid plan change them under Connections.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from importlib import resources
from pathlib import Path
from types import ModuleType
from typing import Any

from .vault import VaultError

PRESETS: dict[str, dict[str, Any]] = {
    "fmp": {
        "label": "Financial Modeling Prep", "base": "https://financialmodelingprep.com/stable",
        "key_in": "query", "key_name": "apikey", "per_minute": 0, "per_day": 250, "cache_minutes": 60,
        "test": "quote?symbol=AAPL", "example": 'tz.api("{name}", "quote", params={{"symbol": "AAPL"}})',
        "note": "Free plan: 250 calls a day. Paid plans: no daily limit, 300 or more a minute.",
    },
    "alphavantage": {
        "label": "Alpha Vantage", "base": "https://www.alphavantage.co",
        "key_in": "query", "key_name": "apikey", "per_minute": 5, "per_day": 25, "cache_minutes": 60,
        "error_keys": ["Error Message", "Information", "Note"],
        "test": "query?function=GLOBAL_QUOTE&symbol=IBM",
        "example": 'tz.api("{name}", "query", params={{"function": "GLOBAL_QUOTE", "symbol": "IBM"}})',
        "note": "Free plan: 25 calls a day, 5 a minute. Paid plans: no daily limit.",
    },
    "twelvedata": {
        "label": "Twelve Data", "base": "https://api.twelvedata.com",
        "key_in": "query", "key_name": "apikey", "per_minute": 8, "per_day": 800, "cache_minutes": 15,
        "error_match": {"status": "error"}, "test": "quote?symbol=AAPL",
        "example": 'tz.api("{name}", "quote", params={{"symbol": "AAPL"}})',
        "note": "Free plan: 8 credits a minute, 800 a day. Some requests cost more than one credit: pass cost=.",
    },
    "finnhub": {
        "label": "Finnhub", "base": "https://finnhub.io/api/v1",
        "key_in": "header", "key_name": "X-Finnhub-Token", "per_minute": 60, "per_day": 0, "cache_minutes": 5,
        "test": "quote?symbol=AAPL", "example": 'tz.api("{name}", "quote", params={{"symbol": "AAPL"}})',
        "note": "Free plan: 60 calls a minute.",
    },
    "eodhd": {
        "label": "EODHD", "base": "https://eodhd.com/api",
        "key_in": "query", "key_name": "api_token", "per_minute": 1000, "per_day": 20, "cache_minutes": 60,
        "headers": {}, "test": "user?fmt=json",
        "example": 'tz.api("{name}", "eod/AAPL.US", params={{"fmt": "json"}})',
        "note": "Free plan: 20 calls a day. Paid plans: 100,000 a day. The test uses the free account check.",
    },
    "massive": {
        "label": "Massive (formerly Polygon.io)", "base": "https://api.polygon.io",
        "key_in": "query", "key_name": "apiKey", "per_minute": 5, "per_day": 0, "cache_minutes": 60,
        "test": "v2/aggs/ticker/AAPL/prev", "example": 'tz.api("{name}", "v2/aggs/ticker/AAPL/prev")',
        "note": "Free plan: 5 calls a minute. Paid plans: no limit (set 0).",
    },
    "tiingo": {
        "label": "Tiingo", "base": "https://api.tiingo.com",
        "key_in": "query", "key_name": "token", "per_minute": 1, "per_day": 900, "cache_minutes": 60,
        "test": "api/test", "example": 'tz.api("{name}", "tiingo/daily/aapl/prices", params={{"startDate": "2024-01-02"}})',
        "note": "Free plan: about 50 calls an hour and 1,000 a day, so one a minute keeps every tool safe.",
    },
    "hfdata": {
        "label": "HF Data Library", "base": "https://api.hfdatalibrary.com/v1",
        "key_in": "header", "key_name": "X-API-Key", "per_minute": 250, "per_day": 0, "cache_minutes": 0,
        "test": "symbols", "example": 'tz.api("{name}", "bars/AAPL", params={{"start": "2024-01-02", "end": "2024-01-02"}})',
        "note": "Free key, 300 calls a minute. The key expires every 30 days: paste the new one here.",
    },
    "github": {
        "label": "GitHub", "base": "https://api.github.com",
        "key_in": "header", "key_name": "Authorization", "key_prefix": "Bearer ", "per_minute": 60, "per_day": 0,
        "cache_minutes": 0, "test": "rate_limit", "example": 'tz.api("{name}", "repos/you/repo/contents/README.md")',
        "note": "Use a fine-grained token for only the repository it needs, with only the permissions it needs.",
    },
    "other": {
        "label": "Another service", "base": "", "key_in": "query", "key_name": "apikey",
        "per_minute": 0, "per_day": 0, "cache_minutes": 15, "test": "",
        "example": 'tz.api("{name}", "path/from/their/docs", params={{...}})',
        "note": "Look in the service's documentation for its address and where the key goes.",
    },
}

_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_LOCAL = re.compile(r"^http://(127\.0\.0\.1|localhost)(:\d+)?(/|$)")
FIELDS = ("preset", "base", "key_in", "key_name", "key_prefix", "key_var", "per_minute", "per_day",
          "cache_minutes", "error_keys", "error_match", "headers", "test")


def check_api(api: dict[str, Any] | None, variables: list[str]) -> dict[str, Any] | None:
    """Validate an api block from the Connections screen. Returns the cleaned block."""
    if not api:
        return None
    preset = str(api.get("preset") or "other")
    if preset not in PRESETS:
        raise VaultError("Unknown kind of web service.")
    base = PRESETS[preset]
    out: dict[str, Any] = {"preset": preset}
    url = str(api.get("base", base["base"]) or "").strip().rstrip("/")
    if not (url.startswith("https://") or _LOCAL.match(url)) or " " in url:
        raise VaultError("The web address must start with https://, for example https://api.example.com/v1.")
    out["base"] = url
    key_in = str(api.get("key_in", base["key_in"]))
    if key_in not in ("query", "header", "none"):
        raise VaultError("Choose where the key goes: in the address, in a header, or not needed.")
    out["key_in"] = key_in
    if key_in != "none":
        key_name = str(api.get("key_name", base["key_name"]) or "").strip()
        if not _NAME.match(key_name):
            raise VaultError("The key's name (for example apikey or X-Api-Key) uses letters, digits, - and _.")
        out["key_name"] = key_name
        out["key_prefix"] = str(api.get("key_prefix", base.get("key_prefix", "")) or "")[:20]
        key_var = str(api.get("key_var") or "")
        if key_var not in variables:
            raise VaultError("Choose which of this connection's values is the key.")
        out["key_var"] = key_var
    for field, label in (("per_minute", "calls a minute"), ("per_day", "calls a day"), ("cache_minutes", "minutes to keep answers")):
        try:
            value = int(api.get(field, base[field]) or 0)
        except (TypeError, ValueError):
            raise VaultError(f"Use a whole number for {label} (0 means no limit).") from None
        if value < 0 or value > 10_000_000:
            raise VaultError(f"Use a number from 0 up for {label}.")
        out[field] = value
    if out["cache_minutes"] > 7 * 24 * 60:
        raise VaultError("Keep answers for at most a week (10080 minutes).")
    for field in ("error_keys", "error_match", "headers"):
        if field in base:
            out[field] = base[field]
    out["test"] = str(api.get("test", base.get("test", "")) or "")[:300]
    return out


def run_config(api: dict[str, Any]) -> dict[str, Any]:
    """What a run gets in TRAPYZE_API_<NAME>: no secrets, only where to send and the limits."""
    return {k: api[k] for k in FIELDS if k in api and k != "test"}


def env_name(connection: str) -> str:
    return "TRAPYZE_API_" + re.sub(r"[^A-Z0-9]", "_", connection.upper())


_helper: ModuleType | None = None


def helper() -> ModuleType:
    """The packaged trapyze_helper, so traPYze and the tools share one gateway."""
    global _helper
    if _helper is None:
        source = resources.files("trapyze") / "resources" / "helper" / "trapyze_helper.py"
        with resources.as_file(source) as path:
            spec = importlib.util.spec_from_file_location("trapyze._gateway", Path(path))
            assert spec and spec.loader
            module = importlib.util.module_from_spec(spec)
            sys.modules["trapyze._gateway"] = module
            spec.loader.exec_module(module)
        _helper = module
    return _helper
