"""Read a script's label: the PEP 723 block at the top of the file.

A traPYze script carries everything the suite needs to know in one comment
block, so a tool stays a single file that can be shared as-is:

    # /// script
    # requires-python = ">=3.11"
    # dependencies = ["pandas"]
    #
    # [tool.trapyze]
    # name = "Stock ranker"
    # description = "Ranks shares on value and momentum."
    #
    # [[tool.trapyze.settings]]
    # key = "top_n"
    # label = "Number of shares"
    # type = "int"
    # default = 25
    # ///

The `requires-python` and `dependencies` keys are standard PEP 723 and are
read by the engine (uv). Everything under `[tool.trapyze]` is ours.
"""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

# The reference regular expression from PEP 723.
_BLOCK_RE = re.compile(
    r"(?m)^# /// (?P<type>[a-zA-Z0-9-]+)$\s(?P<content>(^#(| .*)$\s)+)^# ///$"
)

SETTING_TYPES = ("text", "int", "float", "choice", "bool", "date", "file", "folder")

_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_FLAG_RE = re.compile(r"^--?[A-Za-z0-9][A-Za-z0-9_-]*$")
_TRUE = {"true", "yes", "on", "1", "y"}
_FALSE = {"false", "no", "off", "0", "n"}


class LabelError(ValueError):
    """The label is missing or written wrongly. The message is plain English."""


class SettingError(ValueError):
    """A value the user chose for a setting is not allowed."""


@dataclass
class Setting:
    key: str
    label: str
    type: str
    default: Any = None
    help: str = ""
    options: list[str] = field(default_factory=list)
    min: float | None = None
    max: float | None = None
    required: bool = False
    advanced: bool = False
    flag: str = ""  # the script's own option name; empty means --<key>
    switch: bool = False  # bool only: pass the flag alone when on, nothing when off
    positional: bool = False  # pass the bare value, no flag (commands, dates)
    only_for: dict[str, list[str]] = field(default_factory=dict)  # used only when another setting has one of these values

    @property
    def option(self) -> str:
        return self.flag or f"--{self.key}"

    def coerce(self, raw: Any) -> Any:
        """Turn a raw value (often text typed by the user) into the right type.

        Raises SettingError with a sentence a novice can act on.
        """
        name = self.label
        if raw is None or (isinstance(raw, str) and raw.strip() == ""):
            if self.required:
                raise SettingError(f"{name} needs a value.")
            return None if self.type != "bool" else False

        if self.type == "text":
            return str(raw)

        if self.type in ("int", "float"):
            try:
                if self.type == "int":
                    if isinstance(raw, bool):
                        raise ValueError
                    if isinstance(raw, float) and not raw.is_integer():
                        raise ValueError
                    value: float = int(str(raw).strip()) if isinstance(raw, str) else int(raw)
                else:
                    value = float(str(raw).strip().replace(",", ".")) if isinstance(raw, str) else float(raw)
            except (TypeError, ValueError):
                kind = "a whole number" if self.type == "int" else "a number"
                raise SettingError(f"{name} must be {kind}.") from None
            if self.min is not None and value < self.min:
                raise SettingError(self._range_message())
            if self.max is not None and value > self.max:
                raise SettingError(self._range_message())
            return value

        if self.type == "bool":
            if isinstance(raw, bool):
                return raw
            text = str(raw).strip().lower()
            if text in _TRUE:
                return True
            if text in _FALSE:
                return False
            raise SettingError(f"{name} must be on or off.")

        if self.type == "choice":
            text = str(raw)
            if text not in self.options:
                listed = ", ".join(self.options)
                raise SettingError(f"{name} must be one of: {listed}.")
            return text

        if self.type == "date":
            if isinstance(raw, date):
                return raw.isoformat()
            try:
                return date.fromisoformat(str(raw).strip()).isoformat()
            except ValueError:
                raise SettingError(f"{name} must be a date written as YYYY-MM-DD.") from None

        if self.type in ("file", "folder"):
            path = Path(str(raw)).expanduser()
            if self.type == "file" and not path.is_file():
                raise SettingError(f"{name}: the file {path} wasn't found.")
            if self.type == "folder" and not path.is_dir():
                raise SettingError(f"{name}: the folder {path} wasn't found.")
            return str(path)

        raise SettingError(f"{name} has an unknown type.")  # pragma: no cover

    def _range_message(self) -> str:
        def show(n: float | None) -> str:
            if n is None:
                return ""
            return str(int(n)) if float(n).is_integer() else str(n)

        if self.min is not None and self.max is not None:
            return f"{self.label} must be between {show(self.min)} and {show(self.max)}."
        if self.min is not None:
            return f"{self.label} must be {show(self.min)} or more."
        return f"{self.label} must be {show(self.max)} or less."


@dataclass
class Tool:
    path: Path
    id: str
    name: str
    description: str = ""
    icon: str = "terminal"
    color: str = "blue"
    version: str = "0.0.0"
    requires_python: str | None = None
    dependencies: list[str] = field(default_factory=list)
    settings: list[Setting] = field(default_factory=list)
    writes: list[str] = field(default_factory=list)
    reads: dict[str, str | None] = field(default_factory=dict)  # shared data used, with the oldest it may be
    connections: list[str] = field(default_factory=list)
    warning_codes: list[int] = field(default_factory=list)  # exit codes meaning "done, but have a look"
    group: str | None = None  # the program folder it lives in (scripts/<group>/), if any
    hidden: bool = False  # a script of a program that has no tile of its own (shown under "more scripts")

    def setting(self, key: str) -> Setting:
        for s in self.settings:
            if s.key == key:
                return s
        raise SettingError(f"{self.name} has no setting called '{key}'.")

    def defaults(self) -> dict[str, Any]:
        return {s.key: s.default for s in self.settings}

    def resolve(self, chosen: dict[str, Any] | None = None, places: dict[str, str] | None = None) -> dict[str, Any]:
        """Combine defaults with the user's choices and check every value.

        Collects all problems at once, so the settings pop-up can mark every
        wrong field in one go instead of one per attempt. Settings whose
        `only_for` condition isn't met are left out entirely. `{data}`,
        `{output}`, `{home}`, `{lib}` and `{script_dir}` in text, file and
        folder values are replaced by the real folders from `places`.
        """
        chosen = dict(chosen or {})
        unknown = [k for k in chosen if k not in {s.key for s in self.settings}]
        problems: list[str] = [f"{self.name} has no setting called '{k}'." for k in unknown]
        coerced: dict[str, Any] = {}

        def take(s: Setting) -> None:
            raw = chosen.get(s.key, s.default)
            if places and s.type in ("text", "file", "folder") and isinstance(raw, str):
                filled = expand(raw, places)
                if filled != raw:  # a folder was filled in: tidy the separators for this computer
                    filled = os.path.normpath(filled)
                raw = filled
            try:
                coerced[s.key] = s.coerce(raw)
            except SettingError as exc:
                problems.append(str(exc))

        for s in self.settings:
            if not s.only_for:
                take(s)
        for s in self.settings:
            if s.only_for and self._active(s, coerced):
                take(s)
        if problems:
            raise SettingError("\n".join(problems))
        return {s.key: coerced[s.key] for s in self.settings if s.key in coerced}

    @staticmethod
    def _active(s: Setting, values: dict[str, Any]) -> bool:
        for other, allowed in s.only_for.items():
            value = values.get(other)
            if isinstance(value, bool):
                value = "true" if value else "false"
            if value is None or str(value) not in allowed:
                return False
        return True


_PLACE_RE = re.compile(r"\{(data|output|home|lib|script_dir)\}")


def expand(text: str, places: dict[str, str]) -> str:
    """Replace {data}, {output}, {home}, {lib} and {script_dir} with real folders."""
    return _PLACE_RE.sub(lambda m: places.get(m.group(1), m.group(0)), text)


def find_block(source: str) -> dict[str, Any] | None:
    """Return the parsed `script` metadata block, or None if there is none."""
    matches = [m for m in _BLOCK_RE.finditer(source) if m.group("type") == "script"]
    if len(matches) > 1:
        raise LabelError("The script has more than one '# /// script' block.")
    if not matches:
        return None
    content = "".join(
        line[2:] if line.startswith("# ") else line[1:]
        for line in matches[0].group("content").splitlines(keepends=True)
    )
    try:
        return tomllib.loads(content)
    except tomllib.TOMLDecodeError as exc:
        raise LabelError(f"The label can't be read: {exc}.") from None


def read_tool(path: str | Path, tool_id: str | None = None, group: str | None = None) -> Tool:
    """Read a script file and return its Tool description.

    A script without a label still becomes a tool, named after the file,
    with no settings. That way any existing script can be dropped in.
    """
    path = Path(path)
    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise LabelError(f"{path.name} isn't a readable text file.") from None
    meta = find_block(source) or {}
    ours = meta.get("tool", {}).get("trapyze", {})
    if not isinstance(ours, dict):
        raise LabelError("[tool.trapyze] must be a section, not a single value.")

    tool_id = tool_id or path.stem
    name = ours.get("name") or tool_id.replace("_", " ").replace("-", " ").strip().capitalize()

    deps = meta.get("dependencies", [])
    if not isinstance(deps, list) or not all(isinstance(d, str) for d in deps):
        raise LabelError("'dependencies' must be a list of package names.")

    settings = [_read_setting(raw, i) for i, raw in enumerate(ours.get("settings", []), start=1)]
    keys = [s.key for s in settings]
    duplicates = sorted({k for k in keys if keys.count(k) > 1})
    if duplicates:
        raise LabelError(f"Setting key used twice: {', '.join(duplicates)}.")
    by_key = {s.key: s for s in settings}
    for s in settings:
        for other, allowed in s.only_for.items():
            if other not in by_key or other == s.key:
                raise LabelError(f"Setting '{s.key}' is only_for '{other}', but there's no other setting with that key.")
            target = by_key[other]
            if target.type == "choice":
                wrong = [v for v in allowed if v not in target.options]
                if wrong:
                    raise LabelError(
                        f"Setting '{s.key}' is only_for {other} = {', '.join(wrong)}, which isn't one of its options."
                    )

    tool = Tool(
        path=path,
        id=tool_id,
        name=str(name),
        description=str(ours.get("description", "")),
        icon=str(ours.get("icon", "terminal")),
        color=str(ours.get("color", "blue")),
        version=str(ours.get("version", "0.0.0")),
        requires_python=meta.get("requires-python"),
        dependencies=list(deps),
        settings=settings,
        writes=[str(w) for w in ours.get("writes", [])],
        reads=_read_reads(ours.get("reads", {})),
        connections=[str(c) for c in ours.get("connections", [])],
        warning_codes=_read_codes(ours.get("warning_codes", [])),
        group=group,
    )
    # Defaults must themselves be valid, or the very first run would fail.
    for s in tool.settings:
        if s.default is None:
            continue
        try:
            s.default = s.coerce(s.default) if s.type not in ("file", "folder") else s.default
        except SettingError as exc:
            raise LabelError(f"Default for '{s.key}' is not allowed: {exc}") from None
    return tool


def _read_reads(raw: Any) -> dict[str, str | None]:
    """reads = ["data/prices.sqlite"] or reads = { "data/prices.sqlite" = "1td" }."""
    from .freshness import parse_age

    if isinstance(raw, list) and all(isinstance(r, str) for r in raw):
        return {r: None for r in raw}
    if isinstance(raw, dict):
        out: dict[str, str | None] = {}
        for path, age in raw.items():
            if not isinstance(age, str):
                raise LabelError(f"In 'reads', the age for {path} must be text like \"1d\", \"12h\" or \"1td\".")
            try:
                parse_age(age)
            except ValueError as exc:
                raise LabelError(f"In 'reads', {path}: {exc}") from None
            out[str(path)] = age
        return out
    raise LabelError("'reads' must be a list of files, or a table of file = \"how old it may be\".")


def _read_codes(raw: Any) -> list[int]:
    if not isinstance(raw, list) or not all(isinstance(c, int) and not isinstance(c, bool) and c != 0 for c in raw):
        raise LabelError("'warning_codes' must be a list of exit codes other than 0, for example [2].")
    return list(raw)


def _read_setting(raw: Any, position: int) -> Setting:
    if not isinstance(raw, dict):
        raise LabelError(f"Setting {position} must be a [[tool.trapyze.settings]] section.")
    key = raw.get("key")
    if not key or not isinstance(key, str) or not _KEY_RE.match(key):
        raise LabelError(
            f"Setting {position} needs a 'key' made of letters, digits and _ (for example top_n)."
        )
    kind = raw.get("type", "text")
    if kind not in SETTING_TYPES:
        raise LabelError(
            f"Setting '{key}' has type '{kind}'. Use one of: {', '.join(SETTING_TYPES)}."
        )
    flag = raw.get("flag", "")
    if flag and (not isinstance(flag, str) or not _FLAG_RE.match(flag)):
        raise LabelError(f"Setting '{key}' has flag '{flag}'. A flag looks like --smh-weight.")
    switch = bool(raw.get("switch", False))
    if switch and kind != "bool":
        raise LabelError(f"Setting '{key}' is a switch, so its type must be bool.")
    positional = bool(raw.get("positional", False))
    if positional and (flag or switch):
        raise LabelError(f"Setting '{key}' is positional, so it can't also have a flag or be a switch.")
    only_for_raw = raw.get("only_for", {})
    if not isinstance(only_for_raw, dict):
        raise LabelError(f"Setting '{key}': only_for looks like {{ command = [\"update\", \"prices\"] }}.")
    only_for: dict[str, list[str]] = {}
    for other, allowed in only_for_raw.items():
        allowed = allowed if isinstance(allowed, list) else [allowed]
        only_for[str(other)] = [("true" if a else "false") if isinstance(a, bool) else str(a) for a in allowed]
    options = raw.get("options", [])
    if kind == "choice":
        if not isinstance(options, list) or not options:
            raise LabelError(f"Setting '{key}' is a choice, so it needs a list of options.")
        options = [str(o) for o in options]
    return Setting(
        key=key,
        label=str(raw.get("label") or key.replace("_", " ").capitalize()),
        type=kind,
        default=raw.get("default"),
        help=str(raw.get("help", "")),
        options=options if kind == "choice" else [],
        min=raw.get("min"),
        max=raw.get("max"),
        required=bool(raw.get("required", False)),
        advanced=bool(raw.get("advanced", False)),
        flag=flag or "",
        switch=switch,
        positional=positional,
        only_for=only_for,
    )
