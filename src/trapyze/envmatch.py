"""Sort the keys of one combined .env file into connections, by what the variable names say.

Only names are matched here; the values are read from the file by the caller and go straight into the vault.
"""
from __future__ import annotations

import re
from typing import Any

from .vault import default_variable, looks_secret

# preset -> patterns on the upper-case variable name. First preset that matches wins.
RULES: list[tuple[str, str]] = [
    ("hfdata", r"(^|_)HF(_?DATA)?(_?LIBRARY)?(_|$)|HFDATA"),
    ("tiingo", r"TIINGO"),
    ("fmp", r"(^|_)FMP(_|$)|FINANCIAL_?MODELING"),
    ("alphavantage", r"ALPHA_?VANTAGE|(^|_)AV_(API_)?KEY"),
    ("twelvedata", r"TWELVE_?DATA|(^|_)TD_API"),
    ("finnhub", r"FINNHUB"),
    ("eodhd", r"EODHD|(^|_)EOD_(API_)?(KEY|TOKEN)"),
    ("massive", r"POLYGON|MASSIVE"),
    ("github", r"GITHUB|(^|_)GH_(TOKEN|PAT)|^GIT_TOKEN"),
]
NOT_A_KEY = re.compile(r"(URL|HOST|PORT|USER(NAME)?$|EMAIL|PATH|DIR|REGION|MODEL)", re.I)


PLACEHOLDER = re.compile(r"^(YOUR_|CHANGE_?ME|XXX)", re.I)
MERGE = {"SMTP": "email", "EMAIL": "email", "USER": "email"}  # these prefixes end up in one "email" connection
TRIM = re.compile(r"_(API_?KEY|KEY|TOKEN|SECRET|PASSWORD|JWT_SECRET)$", re.I)


def _group_name(var: str, sizes: dict[str, int]) -> str:
    prefix = var.upper().split("_")[0]
    if prefix in MERGE and var.upper() not in ("USER_EMAIL",) or (prefix == "USER" and var.upper() == "USER_EMAIL"):
        return "email"
    if sizes.get(prefix, 0) >= 2:
        return prefix.lower()
    base = TRIM.sub("", var) or var
    return re.sub(r"[^a-z0-9_-]+", "_", base.lower()).strip("_")[:64] or "imported"


def match(variables: dict[str, str], existing: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """existing: connection name -> {"key_var", "current" (its stored key value or None)}.
    Returns names only: what would be created, changed, left alone, or isn't recognised."""
    items: list[dict[str, Any]] = []
    other: list[dict[str, Any]] = []
    taken: set[str] = set()
    for var, value in variables.items():
        upper = var.upper()
        preset = next((p for p, rx in RULES if re.search(rx, upper)), None)
        if preset and not NOT_A_KEY.search(upper) and looks_secret(var):
            if preset in taken:
                other.append({"name": var, "why": f"A second {preset} key. Only the first is used."})
                continue
            taken.add(preset)
            have = existing.get(preset)
            if have is None:
                action = "new"
            elif have.get("current") == value:
                action = "same"
            else:
                action = "update"
            items.append({"var": var, "preset": preset, "name": preset, "action": action, "empty": not value,
                          "key_var": (have or {}).get("key_var") or default_variable(preset, "API_KEY")})
        else:
            other.append({"name": var, "secret": looks_secret(var), "empty": not value,
                          "why": "Not one of the services traPYze knows."})
    # Everything not recognised becomes its own connection; related variables (same first word) go together.
    sizes: dict[str, int] = {}
    for o in other:
        if o["name"].upper().startswith("YOUR_") or PLACEHOLDER.match(variables.get(o["name"], "")):
            continue
        prefix = o["name"].upper().split("_")[0]
        sizes[prefix] = sizes.get(prefix, 0) + 1
    groups: dict[str, dict[str, Any]] = {}
    skipped: list[dict[str, Any]] = []
    for o in other:
        var = o["name"]
        if o.get("why", "").startswith("A second") or var.upper().startswith("YOUR_") or PLACEHOLDER.match(variables.get(var, "")):
            skipped.append({"name": var, "why": o.get("why") or "Looks like a placeholder, not a real key."})
            continue
        name = _group_name(var, sizes)
        have = existing.get(name)
        if have and have.get("kind") not in (None, "custom"):
            name += "-env"
        g = groups.setdefault(name, {"name": name, "vars": [], "exists": (existing.get(name) or {}).get("values") is not None})
        g["vars"].append({"var": var, "secret": looks_secret(var), "empty": not variables.get(var)})
    out = []
    for g in groups.values():
        cur = (existing.get(g["name"]) or {}).get("values") or {}
        live = [v for v in g["vars"] if not v["empty"]]
        g["action"] = ("new" if not g["exists"] else "same" if all(cur.get(v["var"]) == variables[v["var"]] for v in live) else "update")
        g["empty"] = not live
        out.append(g)
    return {"items": items, "groups": out, "other": skipped}
