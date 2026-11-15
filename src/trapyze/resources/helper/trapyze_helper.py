"""Small helper for traPYze tools. Optional: a tool works without it.

    import trapyze_helper as tz

    s = tz.settings()                      # the values chosen in the settings pop-up
    tz.progress(0.4, "Downloading prices")  # moves the progress bar
    path = tz.output_path("ranking.xlsx")   # where results go; shows on the result card
    db = tz.data_path("prices.db")          # shared data, used by every tool
    r = tz.api("fmp", "quote", params={"symbol": "AAPL"})   # a web service from Connections
    print(r.json())

Outside traPYze (run by hand in a terminal) everything still works: settings
come from --key value arguments, progress prints a plain line, and files go
to the current folder. tz.api() needs traPYze, because the keys live in its vault.

This file belongs to traPYze and is replaced when traPYze is updated.
"""

from __future__ import annotations

import hashlib
import json as _json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

_MARK = "@@trapyze"
__version__ = "0.4.0"


def inside_trapyze() -> bool:
    return "TRAPYZE_RUN_ID" in os.environ


def settings() -> dict[str, Any]:
    """The chosen settings, already checked and converted by traPYze.

    Outside traPYze, reads --key value pairs from the command line as text.
    """
    raw = os.environ.get("TRAPYZE_SETTINGS")
    if raw:
        return _json.loads(raw)
    values: dict[str, Any] = {}
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        arg = args[i]
        if arg.startswith("--"):
            key = arg[2:]
            if "=" in key:
                key, value = key.split("=", 1)
                values[key] = value
            elif i + 1 < len(args) and not args[i + 1].startswith("--"):
                values[key] = args[i + 1]
                i += 1
            else:
                values[key] = "true"
        i += 1
    return values


def progress(fraction: float, message: str = "") -> None:
    """Report progress between 0 and 1, with an optional step in plain words."""
    fraction = max(0.0, min(1.0, float(fraction)))
    print(f"{_MARK} progress {fraction:.3f} {message}".rstrip(), flush=True)


def step(message: str) -> None:
    """Report what the tool is doing now, without a percentage."""
    print(f"{_MARK} step {message}", flush=True)


def output_path(name: str) -> Path:
    """A path for a result file. traPYze collects everything saved here."""
    folder = Path(os.environ.get("TRAPYZE_OUTPUT_DIR", "."))
    folder.mkdir(parents=True, exist_ok=True)
    return folder / name


def data_path(name: str) -> Path:
    """A path in the shared data folder, for databases several tools use."""
    folder = Path(os.environ.get("TRAPYZE_DATA_DIR", "data"))
    folder.mkdir(parents=True, exist_ok=True)
    return folder / name


# ---------------------------------------------------------------------------
# The shared API gateway
#
# Every tool that calls a web service through tz.api() shares one set of
# limits, one cache and one usage count, kept in traPYze's own folder. So two
# tools running at once never go over a service's limit together, and the same
# question asked twice within the cache time costs one call.
# ---------------------------------------------------------------------------

class ApiError(Exception):
    """A web service call that didn't work, explained in plain words."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class ApiLimitReached(ApiError):
    """The service's daily allowance is used up."""


class Response:
    def __init__(self, status: int, headers: dict[str, str], content: bytes, from_cache: bool, url: str):
        self.status = status
        self.headers = headers
        self.content = content
        self.from_cache = from_cache
        self.url = url  # without the key

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    @property
    def text(self) -> str:
        m = re.search(r"charset=([\w-]+)", self.headers.get("content-type", ""), re.I)
        return self.content.decode(m.group(1) if m else "utf-8", errors="replace")

    def json(self) -> Any:
        try:
            return _json.loads(self.text)
        except ValueError:
            raise ApiError(f"The answer from {self.url} isn't JSON. Use .text to see it.") from None

    def __repr__(self) -> str:
        return f"<Response {self.status}{' (cache)' if self.from_cache else ''} {self.url}>"


def _env_name(service: str) -> str:
    return "TRAPYZE_API_" + re.sub(r"[^A-Z0-9]", "_", service.upper())


def api(service: str, path: str = "", params: dict[str, Any] | None = None, *, method: str = "GET",
        headers: dict[str, str] | None = None, json: Any = None, data: bytes | str | dict | None = None,
        cache: bool | float | None = None, cost: int = 1, timeout: float = 30, retries: int = 3) -> Response:
    """Call a web service set up under Connections.

    service  the connection's name, for example "fmp"; the tool's label must ask for it
    path     the part after the service's web address, for example "quote" (or a full address
             on the same site)
    params   extra address parameters, for example {"symbol": "AAPL"}
    cache    None: the connection's setting; False: always ask the service; a number: minutes
    cost     how many calls this counts as, for services that charge some requests more

    The key is added for you. Waits when the shared per-minute limit is reached, and
    raises ApiLimitReached when the daily allowance is used up.
    """
    raw = os.environ.get(_env_name(service))
    if not raw:
        if inside_trapyze():
            raise ApiError(
                f"This tool can't use '{service}' yet. Add connections = [\"{service}\"] to its label, "
                f"and under Connections turn on 'Use with tz.api()' for {service}."
            )
        raise ApiError("tz.api() works when the tool runs from traPYze, which holds the keys.")
    cfg = _json.loads(raw)
    key = os.environ.get(cfg.get("key_var") or "", "") if cfg.get("key_in", "query") != "none" else ""
    if cfg.get("key_in", "query") != "none" and not key:
        raise ApiError(f"The connection '{service}' has no value for {cfg.get('key_var')}. Fill it in under Connections.")
    return call(service, cfg, key, path, params, method=method, headers=headers, json_body=json, data=data,
                cache=cache, cost=cost, timeout=timeout, retries=retries, db=_db_path())


def _db_path() -> Path:
    explicit = os.environ.get("TRAPYZE_API_DB")
    if explicit:
        return Path(explicit)
    home = os.environ.get("TRAPYZE_HOME")
    return Path(home) / ".trapyze" / "api.sqlite" if home else Path(".trapyze-api.sqlite")


def _connect(db: Path) -> sqlite3.Connection:
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db), timeout=60, isolation_level=None)
    con.execute("PRAGMA busy_timeout = 60000")
    try:
        con.execute("PRAGMA journal_mode = WAL")
    except sqlite3.OperationalError:
        pass
    con.executescript("""
        CREATE TABLE IF NOT EXISTS calls (service TEXT, t REAL, n INTEGER);
        CREATE INDEX IF NOT EXISTS calls_st ON calls (service, t);
        CREATE TABLE IF NOT EXISTS usage (service TEXT, day TEXT, calls INTEGER DEFAULT 0, cached INTEGER DEFAULT 0,
            errors INTEGER DEFAULT 0, waited REAL DEFAULT 0, last REAL, PRIMARY KEY (service, day));
        CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, service TEXT, expires REAL, stored REAL,
            status INTEGER, headers TEXT, body BLOB);
        CREATE INDEX IF NOT EXISTS cache_exp ON cache (expires);
    """)
    return con


def _day(t: float) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(t))  # most services count per UTC day


def _bump(con: sqlite3.Connection, service: str, column: str, amount: float = 1) -> None:
    now = time.time()
    con.execute(
        f"INSERT INTO usage (service, day, {column}, last) VALUES (?, ?, ?, ?) "
        f"ON CONFLICT (service, day) DO UPDATE SET {column} = {column} + excluded.{column}, last = excluded.last",
        (service, _day(now), amount, now),
    )


def _reserve(con: sqlite3.Connection, service: str, cfg: dict[str, Any], cost: int) -> None:
    """Take room for one call under the shared limits, waiting if the minute is full."""
    per_minute = int(cfg.get("per_minute") or 0)
    per_day = int(cfg.get("per_day") or 0)
    if per_minute and cost > per_minute:
        raise ApiError(f"One call costing {cost} is more than {service}'s limit of {per_minute} a minute.")
    while True:
        now = time.time()
        con.execute("BEGIN IMMEDIATE")
        try:
            if per_day:
                row = con.execute("SELECT calls FROM usage WHERE service = ? AND day = ?", (service, _day(now))).fetchone()
                used = row[0] if row else 0
                if used + cost > per_day:
                    raise ApiLimitReached(
                        f"{service}'s allowance of {per_day} calls a day is used up ({used} so far). "
                        "It starts again at midnight UTC. A bigger plan? Change the limit under Connections."
                    )
            wait = 0.0
            if per_minute:
                con.execute("DELETE FROM calls WHERE t < ?", (now - 60,))
                used, oldest = con.execute(
                    "SELECT COALESCE(SUM(n), 0), MIN(t) FROM calls WHERE service = ?", (service,)).fetchone()
                if used + cost > per_minute:
                    wait = max(0.05, oldest + 60 - now + 0.05)
            if not wait:
                con.execute("INSERT INTO calls (service, t, n) VALUES (?, ?, ?)", (service, now, cost))
                _bump(con, service, "calls", cost)
                con.execute("COMMIT")
                return
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK")
            raise
        if wait > 1.5:
            step(f"Waiting {wait:.0f} s: {service} allows {per_minute} calls a minute")
        time.sleep(wait)
        _bump(con, service, "waited", wait)


def _hide(text: str, key: str) -> str:
    return text.replace(key, "••••••") if key and len(key) >= 4 else text


def _soft_error(cfg: dict[str, Any], body: bytes) -> str | None:
    """Some services answer 200 OK with an error message inside. Return it, if so."""
    keys = cfg.get("error_keys") or []
    match = cfg.get("error_match") or {}
    if not keys and not match:
        return None
    try:
        found = _json.loads(body.decode("utf-8", errors="replace"))
    except ValueError:
        return None
    if not isinstance(found, dict):
        return None
    for k in keys:
        if k in found:
            return str(found[k])
    if match and all(found.get(k) == v for k, v in match.items()):
        return str(found.get("message") or found)
    return None


def call(service: str, cfg: dict[str, Any], key: str, path: str = "", params: dict[str, Any] | None = None, *,
         method: str = "GET", headers: dict[str, str] | None = None, json_body: Any = None,
         data: bytes | str | dict | None = None, cache: bool | float | None = None, cost: int = 1,
         timeout: float = 30, retries: int = 3, db: Path | None = None) -> Response:
    """The gateway itself; tz.api() fills in the settings and the key. traPYze uses it for Test."""
    base = str(cfg.get("base") or "").rstrip("/")
    if not base:
        raise ApiError(f"The connection '{service}' has no web address. Fill it in under Connections.")
    if path.startswith(("http://", "https://")):
        if not (path == base or path.startswith(base + "/") or path.startswith(base + "?")):
            raise ApiError(f"{path.split('?')[0]} isn't on {service}'s site ({base}), so traPYze won't send the key there.")
        url = path
    else:
        url = base + ("/" + path.lstrip("/") if path else "")
    parts = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    for k, v in (params or {}).items():
        if v is None:
            continue
        for item in (v if isinstance(v, (list, tuple)) else [v]):
            query.append((k, "true" if item is True else "false" if item is False else str(item)))
    key_in, key_name = cfg.get("key_in", "query"), cfg.get("key_name") or "apikey"
    send_headers = {"User-Agent": "traPYze", "Accept": "*/*", **(cfg.get("headers") or {}), **(headers or {})}
    public_query = [(k, v) for k, v in query if not (key_in == "query" and k == key_name)]
    if key_in == "query":
        query = public_query + [(key_name, key)]
    elif key_in == "header":
        send_headers[key_name] = (cfg.get("key_prefix") or "") + key
    public_url = urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(public_query)))
    real_url = urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))

    payload: bytes | None = None
    if json_body is not None:
        payload = _json.dumps(json_body).encode("utf-8")
        send_headers.setdefault("Content-Type", "application/json")
    elif isinstance(data, dict):
        payload = urllib.parse.urlencode(data).encode("utf-8")
        send_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    elif isinstance(data, str):
        payload = data.encode("utf-8")
    elif data is not None:
        payload = bytes(data)
    method = method.upper()

    minutes = float(cfg.get("cache_minutes") or 0) if cache is None or cache is True else float(cache or 0)
    if cache is True and not minutes:
        minutes = 60
    use_cache = method == "GET" and payload is None and minutes > 0
    shown_headers = sorted((k, v) for k, v in send_headers.items() if not (key_in == "header" and k == key_name))
    cache_key = hashlib.sha256(f"{service}\n{method}\n{public_url}\n{shown_headers}".encode()).hexdigest()

    con = _connect(db or _db_path())
    try:
        if use_cache:
            row = con.execute("SELECT status, headers, body, stored FROM cache WHERE key = ? AND expires > ?",
                              (cache_key, time.time())).fetchone()
            if row and row[3] >= time.time() - minutes * 60:
                _bump(con, service, "cached")
                return Response(row[0], _json.loads(row[1]), row[2], True, public_url)

        attempt = 0
        while True:
            attempt += 1
            _reserve(con, service, cfg, cost)
            request = urllib.request.Request(real_url, data=payload, headers=send_headers, method=method)
            retry_after: float | None = None
            try:
                with urllib.request.urlopen(request, timeout=timeout) as answer:
                    status, got_headers, body = answer.status, {k.lower(): v for k, v in answer.headers.items()}, answer.read()
            except urllib.error.HTTPError as exc:
                status, got_headers = exc.code, {k.lower(): v for k, v in (exc.headers or {}).items()}
                body = exc.read() if exc.fp else b""
                exc.close()
            except (urllib.error.URLError, OSError) as exc:
                _bump(con, service, "errors")
                reason = getattr(exc, "reason", exc)
                if attempt <= retries and "timed out" in str(reason).lower():
                    time.sleep(2 * attempt)
                    continue
                raise ApiError(_hide(f"Couldn't reach {service} ({parts.netloc}): {reason}. Check the internet connection.", key)) from None

            soft = _soft_error(cfg, body) if 200 <= status < 300 else None
            if status == 429 or (soft and re.search(r"per minute|frequency|too many|rate limit", soft, re.I)
                                 and not re.search(r"per day|daily", soft, re.I)):
                _bump(con, service, "errors")
                if attempt <= retries:
                    try:
                        retry_after = float(got_headers.get("retry-after", ""))
                    except ValueError:
                        retry_after = None
                    wait = min(retry_after if retry_after is not None else 10 * 2 ** (attempt - 1), 120)
                    step(f"{service} asks to slow down; trying again in {wait:.0f} s")
                    time.sleep(wait)
                    continue
                raise ApiError(f"{service} keeps saying 'too many requests'. Lower its limit under Connections.", status)
            if soft:
                _bump(con, service, "errors")
                if re.search(r"per day|daily", soft, re.I):
                    raise ApiLimitReached(_hide(f"{service} says its daily allowance is used up: {soft}", key), status)
                raise ApiError(_hide(f"{service} answered with a problem: {soft}", key), status)
            if not 200 <= status < 300:
                _bump(con, service, "errors")
                hint = {401: "The key was refused. Check it under Connections.",
                        403: "The key was refused, or your plan doesn't include this.",
                        404: "That address doesn't exist on this service. Check the path.",
                        }.get(status, "The service had a problem; try again later." if status >= 500 else "")
                snippet = body[:300].decode("utf-8", errors="replace").strip()
                raise ApiError(_hide(f"{service} answered {status} for {public_url}. {hint}"
                                     + (f" It said: {snippet}" if snippet else ""), key), status)
            if use_cache and len(body) <= 50 * 1024 * 1024:
                now = time.time()
                con.execute("DELETE FROM cache WHERE expires < ?", (now,))
                con.execute("INSERT OR REPLACE INTO cache VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (cache_key, service, now + minutes * 60, now, status, _json.dumps(got_headers), body))
            return Response(status, got_headers, body, False, public_url)
    finally:
        con.close()


def usage(db: Path | None = None, day: str | None = None) -> dict[str, dict[str, Any]]:
    """Today's count per service (UTC day): calls, answers from the cache, problems, seconds waited."""
    path = db or _db_path()
    if not path.exists():
        return {}
    con = _connect(path)
    try:
        rows = con.execute("SELECT service, calls, cached, errors, waited, last FROM usage WHERE day = ?",
                           (day or _day(time.time()),)).fetchall()
        stored = dict(con.execute("SELECT service, COUNT(*) FROM cache WHERE expires > ? GROUP BY service", (time.time(),)).fetchall())
    finally:
        con.close()
    out = {r[0]: {"calls": r[1], "cached": r[2], "errors": r[3], "waited": round(r[4] or 0), "last": r[5]} for r in rows}
    for name, n in stored.items():
        out.setdefault(name, {"calls": 0, "cached": 0, "errors": 0, "waited": 0, "last": None})["stored"] = n
    return out


def clear_cache(service: str, db: Path | None = None) -> int:
    path = db or _db_path()
    if not path.exists():
        return 0
    con = _connect(path)
    try:
        return con.execute("DELETE FROM cache WHERE service = ?", (service,)).rowcount
    finally:
        con.close()
