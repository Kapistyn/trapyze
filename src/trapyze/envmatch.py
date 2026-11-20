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
    return {"items": items, "other": other}
