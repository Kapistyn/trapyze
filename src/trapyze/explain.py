"""Turn a failed run into one plain sentence and one suggested action.

The full technical output is always kept in the run's log; this only picks
what a novice sees first.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Explanation:
    cause: str
    action: str


_RULES: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(r"No module named '([^'.]+)"),
        "Something this tool needs is missing: the package '{0}'.",
        "Add \"{0}\" to the tool's dependencies, or ask its author to.",
    ),
    # The engine's own download errors come first: they look like connection
    # errors too, but the fix a novice needs is different.
    (
        re.compile(r"Failed to (download|fetch)[^\n]*(pypi|files\.pythonhosted|python-build)", re.I),
        "The packages this tool needs couldn't be downloaded.",
        "Check that you're online. A tool's first run needs the internet once; after that it works offline.",
    ),
    (
        re.compile(
            r"(ConnectionError|ConnectTimeout|ReadTimeout|URLError|Name or service not known|"
            r"getaddrinfo failed|Temporary failure in name resolution|Failed to establish a new connection|"
            r"Network is unreachable|nodename nor servname)",
            re.I,
        ),
        "The tool couldn't connect to the internet or to a service it uses.",
        "Check that you're online, then try again.",
    ),
    (
        re.compile(r"No solution found when resolving|Because .* depends on", re.I),
        "The packages this tool asks for don't fit together.",
        "Ask the tool's author to check its dependencies.",
    ),
    (
        re.compile(r"FileNotFoundError: .*?'([^']+)'"),
        "A file the tool needed wasn't found: {0}",
        "Check that the file exists, or pick another one in the settings.",
    ),
    (
        re.compile(r"PermissionError: .*?'([^']+)'"),
        "The tool wasn't allowed to open {0}",
        "Close the file if it's open in another program, then try again.",
    ),
    (
        re.compile(r"MemoryError"),
        "The computer ran out of memory.",
        "Close other programs, or try smaller settings.",
    ),
    (
        re.compile(r"requires a different Python|does not satisfy Python requirement|No interpreter found", re.I),
        "This tool needs a different Python version than the one available.",
        "Check the tool's requires-python line, or let the engine install that version once online.",
    ),
]


def explain(exit_code: int | None, output_tail: list[str], cancelled: bool = False) -> Explanation:
    if cancelled:
        return Explanation("Stopped by you.", "Run it again whenever you like.")
    text = "\n".join(output_tail)
    for pattern, cause, action in _RULES:
        match = pattern.search(text)
        if match:
            groups = [g for g in match.groups() if g] or [""]
            return Explanation(cause.format(*groups), action.format(*groups))
    last = next((line.strip() for line in reversed(output_tail) if line.strip()), "")
    detail = f" The last message was: {last}" if last else ""
    return Explanation(
        f"The tool stopped with an error (code {exit_code}).{detail}",
        "Use 'copy details' to ask an AI or the tool's author what went wrong.",
    )
