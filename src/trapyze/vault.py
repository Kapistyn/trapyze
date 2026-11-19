"""The vault: API keys and logins, entered once, kept encrypted on this computer.

How it's protected
  * Everything is encrypted with AES-256-GCM (the `cryptography` package).
  * The key comes from two parts, both needed:
      1. your PIN or passphrase, stretched with scrypt (slow on purpose), and
      2. a random device key that only your computer account can read
         (Windows: protected by DPAPI; macOS/Linux: a file only you can read).
    So a copy of the vault file alone is useless, and so is the device key alone.
  * Connections marked "available to scheduled plans" are also kept in a second
    store that needs only the device key, so a plan can run while nobody is
    there to type the PIN. That store is as safe as your computer login.

What tools get
  A connection is a small set of environment variables, for example
  FMP_API_KEY=... . A tool that lists the connection in its label
  (connections = ["fmp"]) receives those variables when it runs, after you
  allowed it once. The values are blanked out of its output and logs.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
import datetime as _dt
from datetime import datetime
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

VERSION = 1
AAD = b"trapyze-vault-v1"
AWAY_AAD = b"trapyze-away-v1"
SCRYPT = {"n": 2**15, "r": 8, "p": 1}
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
VAR_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,99}$")
MIN_PIN = 6


class VaultError(ValueError):
    """Something about the vault, said in plain words."""


class Locked(VaultError):
    pass


class WrongPin(VaultError):
    pass


TEMPLATES: dict[str, dict[str, Any]] = {
    "api_key": {
        "label": "Data service (API key)",
        "hint": "Prices, news, weather and other web services that give you a key.",
        "variables": [{"suffix": "API_KEY", "label": "Key", "secret": True}],
        "scheduled": True,
    },
    "login": {
        "label": "Login (user name and password)",
        "hint": "A database, a website or another service with a user name and password.",
        "variables": [
            {"suffix": "USER", "label": "User name or email", "secret": False},
            {"suffix": "PASSWORD", "label": "Password", "secret": True},
        ],
        "scheduled": True,
    },
    "email": {
        "label": "Email for sending",
        "hint": "Lets tools send you messages. For Gmail use an app password, not your normal one.",
        "variables": [
            {"name": "SMTP_HOST", "label": "Mail server", "secret": False, "example": "smtp.gmail.com"},
            {"name": "SMTP_PORT", "label": "Port", "secret": False, "example": "587"},
            {"name": "SMTP_USER", "label": "User name or email", "secret": False},
            {"name": "SMTP_PASS", "label": "Password or app password", "secret": True},
            {"name": "SMTP_TO", "label": "Send messages to", "secret": False},
        ],
        "scheduled": True,
        "testable": True,
    },
    "sensitive": {
        "label": "Broker or bank login",
        "hint": "Treated as sensitive: only available while you're at the computer.",
        "variables": [
            {"suffix": "USER", "label": "User name", "secret": False},
            {"suffix": "PASSWORD", "label": "Password", "secret": True},
        ],
        "scheduled": False,
    },
    "custom": {
        "label": "Something else",
        "hint": "Any set of variables a script expects, for example from its .env file.",
        "variables": [],
        "scheduled": True,
    },
}


# ---------------------------------------------------------------- device key
def _dpapi(data: bytes, protect: bool) -> bytes:  # pragma: no cover - Windows only
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = BLOB()
    crypt32 = ctypes.windll.crypt32
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    ok = fn(ctypes.byref(blob_in), None, None, None, None, 0x01, ctypes.byref(blob_out))  # UI_FORBIDDEN
    if not ok:
        raise VaultError("Windows refused to unlock traPYze's device key for this account.")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def device_key(folder: Path) -> bytes:
    """A random key only this computer account can read. Created on first use."""
    path = folder / "device.key"
    if path.exists():
        raw = path.read_bytes()
        return _dpapi(raw, protect=False) if sys.platform == "win32" else base64.b64decode(raw)
    key = os.urandom(32)
    folder.mkdir(parents=True, exist_ok=True)
    stored = _dpapi(key, protect=True) if sys.platform == "win32" else base64.b64encode(key)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(stored)
    return key


# ---------------------------------------------------------------- helpers
def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _unb64(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))


def _seal(key: bytes, data: dict, aad: bytes) -> dict[str, str]:
    nonce = os.urandom(12)
    box = AESGCM(key).encrypt(nonce, json.dumps(data).encode("utf-8"), aad)
    return {"nonce": _b64(nonce), "box": _b64(box)}


def _open(key: bytes, sealed: dict[str, str], aad: bytes) -> dict:
    plain = AESGCM(key).decrypt(_unb64(sealed["nonce"]), _unb64(sealed["box"]), aad)
    return json.loads(plain.decode("utf-8"))


def _write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def default_variable(name: str, suffix: str) -> str:
    base = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").upper() or "MY"
    if base[0].isdigit():
        base = "X" + base
    return f"{base}_{suffix}"


def parse_env_file(path: str | Path) -> dict[str, str]:
    """Read KEY=VALUE lines, as in a .env file. Comments and blank lines are skipped."""
    values: dict[str, str] = {}
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if VAR_RE.match(key):
            values[key] = value
    return values


def looks_secret(variable: str) -> bool:
    return bool(re.search(r"(KEY|SECRET|TOKEN|PASS|PWD|PIN|CREDENTIAL)", variable.upper()))


# ---------------------------------------------------------------- the vault
def renewal_info(renewed: str | None, renew_days: int | None, today: _dt.date | None = None) -> dict[str, Any] | None:
    """When a key that's renewed every renew_days days runs out, counted from the day it was last saved."""
    if not renew_days or not renewed:
        return None
    try:
        since = _dt.date.fromisoformat(str(renewed)[:10])
    except ValueError:
        return None
    due = since + _dt.timedelta(days=int(renew_days))
    left = (due - (today or _dt.date.today())).days
    return {"renew_days": int(renew_days), "renewed": since.isoformat(), "expires": due.isoformat(), "days_left": left,
            "due": left <= REMIND_DAYS}


REMIND_DAYS = 5  # start reminding this many days before a key runs out


@dataclass
class Vault:
    folder: Path
    _key: bytes | None = None
    _data: dict[str, Any] = field(default_factory=dict)
    _failures: int = 0
    _last_used: float = 0.0

    @property
    def path(self) -> Path:
        return self.folder / "vault.json"

    @property
    def away_path(self) -> Path:
        return self.folder / "vault-away.json"

    @property
    def renewals_path(self) -> Path:
        """Names and renewal dates only (no secrets), so reminders work while the vault is locked."""
        return self.folder / "renewals.json"

    def exists(self) -> bool:
        return self.path.exists()

    def renewals(self, today: _dt.date | None = None) -> list[dict[str, Any]]:
        """Connections whose key must be renewed every so many days, soonest first."""
        try:
            data = json.loads(self.renewals_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        today = today or _dt.date.today()
        out = []
        for name, r in data.items():
            info = renewal_info(r.get("renewed"), r.get("renew_days"), today)
            if info:
                out.append({"name": name, **info})
        return sorted(out, key=lambda r: r["days_left"])

    @property
    def unlocked(self) -> bool:
        return self._key is not None

    # Opening and closing -----------------------------------------------------
    def _derive(self, pin: str, salt: bytes) -> bytes:
        stretched = hashlib.scrypt(pin.encode("utf-8"), salt=salt, dklen=32, maxmem=128 * 1024 * 1024, **SCRYPT)
        return hmac.new(device_key(self.folder), b"vault|" + stretched, hashlib.sha256).digest()

    def create(self, pin: str) -> None:
        if self.exists():
            raise VaultError("There's already a vault. Unlock it, or reset it to start again.")
        _check_pin(pin)
        salt = os.urandom(16)
        self._key = self._derive(pin, salt)
        self._data = {"connections": {}, "allowed": {}}
        self._meta = {"version": VERSION, "kdf": {"name": "scrypt", **SCRYPT}, "salt": _b64(salt), "created": _now()}
        self._save()
        self.touch()  # a new vault is open and in use, not idle since the computer started

    def unlock(self, pin: str) -> None:
        if not self.exists():
            raise VaultError("There's no vault yet.")
        if self._failures >= 3:
            time.sleep(min(30, 2 ** (self._failures - 2)))  # slow down guessing
        stored = json.loads(self.path.read_text(encoding="utf-8"))
        key = self._derive(pin, _unb64(stored["salt"]))
        try:
            data = _open(key, stored["sealed"], AAD)
        except InvalidTag:
            self._failures += 1
            raise WrongPin("That PIN isn't right. Try again.") from None
        self._failures = 0
        self._key, self._data = key, data
        self._meta = {k: v for k, v in stored.items() if k != "sealed"}
        self.touch()
        self._adopt_renewals()

    def _adopt_renewals(self) -> None:
        """Connections made before reminders existed, for a service whose keys run out (HF Data Library):
        remind from the day the key was last saved."""
        from .apis import PRESETS
        changed = False
        for c in self._data.get("connections", {}).values():
            days = PRESETS.get((c.get("api") or {}).get("preset") or "", {}).get("renew_days")
            if days and not c.get("renew_days"):
                c["renew_days"], c["renewed"] = days, c.get("renewed") or c.get("updated") or _now()
                changed = True
        if changed:
            self._save()

    def lock(self) -> None:
        self._key = None
        self._data = {}

    def touch(self) -> None:
        self._last_used = time.monotonic()

    def idle_seconds(self) -> float:
        return time.monotonic() - self._last_used if self.unlocked else 0.0

    def change_pin(self, old: str, new: str) -> None:
        self.unlock(old)
        _check_pin(new)
        salt = os.urandom(16)
        self._key = self._derive(new, salt)
        self._meta["salt"] = _b64(salt)
        self._save()

    def reset(self) -> None:
        """Forget everything. Used when the PIN is lost: the keys can't be recovered."""
        self.lock()
        for p in (self.path, self.away_path):
            p.unlink(missing_ok=True)

    def _need(self) -> None:
        if not self.unlocked:
            raise Locked("The vault is locked. Unlock it with your PIN first.")
        self.touch()

    def _save(self) -> None:
        assert self._key is not None
        self.folder.mkdir(parents=True, exist_ok=True)
        _write_json(self.path, {**self._meta, "sealed": _seal(self._key, self._data, AAD)})
        away = {n: c for n, c in self._data["connections"].items() if c.get("scheduled")}
        away_key = hmac.new(device_key(self.folder), b"away", hashlib.sha256).digest()
        _write_json(self.away_path, {"version": VERSION, "sealed": _seal(away_key, {"connections": away}, AWAY_AAD)})
        _write_json(self.renewals_path, {n: {"renew_days": c["renew_days"], "renewed": c.get("renewed")}
                                         for n, c in self._data["connections"].items() if c.get("renew_days")})

    # Connections -------------------------------------------------------------
    def connections(self) -> list[dict[str, Any]]:
        """Everything about each connection except the secret values."""
        self._need()
        out = []
        for name, c in sorted(self._data["connections"].items()):
            out.append({
                "name": name, "kind": c["kind"], "description": c.get("description", ""),
                "variables": [
                    {"name": v, "secret": v in c["secret"], "value": None if v in c["secret"] else c["values"][v],
                     "set": bool(c["values"][v])}
                    for v in c["values"]
                ],
                "scheduled": c.get("scheduled", False), "created": c.get("created"), "updated": c.get("updated"),
                "tested": c.get("tested"), "test_ok": c.get("test_ok"), "api": c.get("api"),
                "allowed": sorted(t for t, names in self._data["allowed"].items() if name in names),
                "renew_days": c.get("renew_days"), "renewed": c.get("renewed"),
                "renewal": renewal_info(c.get("renewed"), c.get("renew_days")),
            })
        return out

    def save_connection(self, name: str, kind: str, values: dict[str, str | None], secret: list[str],
                        scheduled: bool, description: str = "", replace_from: str | None = None,
                        api: dict[str, Any] | None = None, renew_days: int | None = None) -> None:
        """Add or change a connection. A value of None keeps the stored value (for editing).
        renew_days: the key must be renewed that often (HF Data Library: 30); traPYze reminds you."""
        self._need()
        name = name.strip().lower()
        if not NAME_RE.match(name):
            raise VaultError("A connection name uses lowercase letters, digits, - and _, for example 'fmp' or 'gmail'.")
        if kind not in TEMPLATES:
            raise VaultError("Unknown kind of connection.")
        bad = [v for v in values if not VAR_RE.match(v)]
        if bad:
            raise VaultError(f"Variable names use letters, digits and _, and don't start with a digit: {', '.join(bad)}.")
        if not values:
            raise VaultError("A connection needs at least one value.")
        conns = self._data["connections"]
        if replace_from is None and name in conns:
            raise VaultError(f"There's already a connection called '{name}'. Edit that one instead.")
        if replace_from is not None and replace_from not in conns:
            raise VaultError(f"There's no connection called '{replace_from}'.")
        if replace_from is not None and replace_from != name and name in conns:
            raise VaultError(f"There's already a connection called '{name}'.")
        old = conns.get(replace_from) if replace_from else None
        merged = {}
        for var, value in values.items():
            if value is None:
                if not old or var not in old["values"]:
                    raise VaultError(f"{var} needs a value.")
                merged[var] = old["values"][var]
            else:
                merged[var] = str(value)
        record = {
            "kind": kind, "description": description.strip(), "values": merged,
            "secret": sorted(v for v in merged if v in set(secret)), "scheduled": bool(scheduled),
            "created": (old or {}).get("created", _now()), "updated": _now(),
            "tested": None, "test_ok": None,
        }
        if renew_days:
            if not 1 <= int(renew_days) <= 3650:
                raise VaultError("Renew every: a number of days from 1 to 3650.")
            record["renew_days"] = int(renew_days)
        # The renewal clock restarts when a secret value changes, not when a label or a limit does.
        changed = old is None or any(merged[v] != old["values"].get(v) for v in record["secret"])
        record["renewed"] = _now() if changed else old.get("renewed") or old.get("updated") or _now()
        if api:
            from .apis import check_api
            record["api"] = check_api(api, list(merged))
        if replace_from and replace_from != name:
            conns.pop(replace_from, None)
            for tool, names in self._data["allowed"].items():
                self._data["allowed"][tool] = [name if n == replace_from else n for n in names]
        conns[name] = record
        self._save()

    def delete_connection(self, name: str) -> None:
        self._need()
        if self._data["connections"].pop(name, None) is None:
            raise VaultError(f"There's no connection called '{name}'.")
        for tool in list(self._data["allowed"]):
            self._data["allowed"][tool] = [n for n in self._data["allowed"][tool] if n != name]
        self._save()

    def record_test(self, name: str, ok: bool) -> None:
        self._need()
        c = self._data["connections"][name]
        c["tested"], c["test_ok"] = _now(), ok
        self._save()

    def api_config(self, name: str) -> dict[str, Any] | None:
        self._need()
        c = self._data["connections"].get(name)
        return dict(c["api"]) if c and c.get("api") else None

    def secret_names(self, name: str) -> list[str]:
        self._need()
        return list(self._data["connections"][name]["secret"])

    def values(self, name: str) -> dict[str, str]:
        self._need()
        try:
            return dict(self._data["connections"][name]["values"])
        except KeyError:
            raise VaultError(f"There's no connection called '{name}'.") from None

    # Permissions ---------------------------------------------------------------
    def allowed(self, tool_id: str) -> set[str]:
        self._need()
        return set(self._data["allowed"].get(tool_id, []))

    def allow(self, tool_id: str, names: list[str]) -> None:
        self._need()
        current = set(self._data["allowed"].get(tool_id, []))
        self._data["allowed"][tool_id] = sorted(current | set(names))
        self._save()

    def disallow(self, tool_id: str, name: str) -> None:
        self._need()
        self._data["allowed"][tool_id] = [n for n in self._data["allowed"].get(tool_id, []) if n != name]
        self._save()

    # Unattended -------------------------------------------------------------
    def away_values(self, name: str) -> tuple[dict[str, str], list[str], dict[str, Any] | None] | None:
        """For scheduled runs with nobody there: values if the connection is marked
        'available to scheduled plans', else None. Needs no PIN."""
        try:
            stored = json.loads(self.away_path.read_text(encoding="utf-8"))
            key = hmac.new(device_key(self.folder), b"away", hashlib.sha256).digest()
            data = _open(key, stored["sealed"], AWAY_AAD)
        except (OSError, ValueError, KeyError, InvalidTag):
            return None
        c = data["connections"].get(name)
        return (dict(c["values"]), list(c["secret"]), c.get("api")) if c else None


def _check_pin(pin: str) -> None:
    if len(pin) < MIN_PIN:
        raise VaultError(f"Use at least {MIN_PIN} characters. A longer passphrase is even safer.")
    if pin.isdigit() and len(set(pin)) == 1:
        raise VaultError("Pick a PIN that isn't one digit repeated.")
    if pin.isdigit() and (pin in "01234567890123456789" or pin in "98765432109876543210"):
        raise VaultError("Pick a PIN that isn't a simple run like 123456.")


# ---------------------------------------------------------------- for runs
class NeedsUnlock(VaultError):
    pass


class NeedsPermission(VaultError):
    def __init__(self, tool_name: str, names: list[str]):
        self.names = names
        super().__init__(f"{tool_name} wants to use: {', '.join(names)}. Allow it first.")


def secrets_for(vault: Vault, tool_id: str, tool_name: str, wanted: list[str], unattended: bool = False) -> tuple[dict[str, str], list[str]]:
    """The environment variables a tool gets, and the values to blank out of its output.

    Raises NeedsUnlock, NeedsPermission or VaultError with a plain message.
    """
    if not wanted:
        return {}, []
    if not vault.exists():
        raise VaultError(f"{tool_name} needs {', '.join(wanted)}, but there's no vault yet. Set one up under Connections.")
    env: dict[str, str] = {}
    if unattended and not vault.unlocked:
        missing, secret = [], []
        for name in wanted:
            found = vault.away_values(name)
            if found is None:
                missing.append(name)
            else:
                env.update(found[0])
                secret += found[1]
                _add_api(env, name, found[2])
        if missing:
            raise VaultError(
                f"{tool_name} needs {', '.join(missing)}, which only works while you're at the computer "
                "(not marked 'available to scheduled plans')."
            )
        # Permission was given when the plan was made; the away store holds no permission list.
        return env, _maskable(env, secret)
    if not vault.unlocked:
        raise NeedsUnlock(f"{tool_name} needs {', '.join(wanted)}. Unlock the vault with your PIN first.")
    known = {c["name"] for c in vault.connections()}
    unknown = [n for n in wanted if n not in known]
    if unknown:
        raise VaultError(
            f"{tool_name} needs a connection called {', '.join(repr(n) for n in unknown)}, "
            "which isn't set up yet. Add it under Connections."
        )
    not_allowed = [n for n in wanted if n not in vault.allowed(tool_id)]
    if not_allowed:
        raise NeedsPermission(tool_name, not_allowed)
    secret: list[str] = []
    for name in wanted:
        env.update(vault.values(name))
        secret += vault.secret_names(name)
        _add_api(env, name, vault.api_config(name))
    return env, _maskable(env, secret)


def _add_api(env: dict[str, str], name: str, api: dict[str, Any] | None) -> None:
    """Tell tz.api() in the run how to reach this connection's service."""
    if api:
        from .apis import env_name, run_config
        env[env_name(name)] = json.dumps(run_config(api))


def _maskable(env: dict[str, str], secret: list[str]) -> list[str]:
    """Values to blank out of output: every secret variable, and any whose name looks secret."""
    chosen = {v for k, v in env.items() if (k in secret or looks_secret(k)) and len(v) >= 4}
    return sorted(chosen, key=len, reverse=True)


def mask(line: str, secrets: list[str]) -> str:
    for s in secrets:
        if s in line:
            line = line.replace(s, "••••••")
    return line
