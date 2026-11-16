"""AI help: explain a script, say why a run failed, make a script traPYze-ready, or change it.

Two ways, both optional:
- copy and paste: traPYze writes the full question, you paste it into any AI chat
  (Copilot, Gemini, ChatGPT, Claude …) and paste the answer back. Free, no setup.
- built in: with a key in the vault for Google Gemini, OpenRouter, Anthropic or
  OpenAI, traPYze asks the AI itself.

Either way, keys and passwords are masked before anything leaves the computer, and
a changed script is only written after you have seen the differences; the old
version is kept (see versions.py).
"""

from __future__ import annotations

import json
import re
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from .health import KEY_NAME, PLACEHOLDER, SECRET_NAME, SECRET_PATTERNS
from .label import LabelError, read_tool
from .store import _read, _write

MASK = "••••"
MAX_SCRIPT = 150_000

PROVIDERS: dict[str, dict[str, Any]] = {
    "gemini": {"name": "Google Gemini", "api": "openai", "base": "https://generativelanguage.googleapis.com/v1beta/openai",
               "keys": "https://aistudio.google.com/apikey",
               "hint": "Free key from Google AI Studio, no card needed. Free use has daily limits, and Google may use "
                       "what you send to improve its products."},
    "openrouter": {"name": "OpenRouter", "api": "openai", "base": "https://openrouter.ai/api/v1",
                   "keys": "https://openrouter.ai/keys",
                   "hint": "One key for the models of many companies. Free models (ending in :free) have low daily "
                           "limits; others are paid per use from credit you add."},
    "anthropic": {"name": "Anthropic (Claude)", "api": "anthropic", "base": "https://api.anthropic.com/v1",
                  "keys": "https://console.anthropic.com/settings/keys", "hint": "Paid per use from credit you add."},
    "openai": {"name": "OpenAI (ChatGPT)", "api": "openai", "base": "https://api.openai.com/v1",
               "keys": "https://platform.openai.com/api-keys", "hint": "Paid per use from credit you add."},
}
CHAT_SITES = {
    "copilot": ("Microsoft Copilot", "https://copilot.microsoft.com/"),
    "gemini": ("Google Gemini", "https://gemini.google.com/app"),
    "aimode": ("Google AI Mode", "https://www.google.com/search?udm=50"),
    "chatgpt": ("ChatGPT", "https://chatgpt.com/"),
    "claude": ("Claude", "https://claude.ai/new"),
}
TASKS = {
    "explain": "Explain this script",
    "why": "Why did it fail?",
    "ready": "Make it traPYze-ready",
    "change": "Change it",
}
CHANGES_CODE = {"ready", "change", "why"}

RULES = """You help someone who is not a programmer with a Python script that runs in traPYze, a desktop
launcher for Python tools. Answer in plain, friendly English; explain any technical word you use.

How a traPYze tool works:
- The file starts with a PEP 723 block (`# /// script` … `# ///`) listing `requires-python` and all
  `dependencies`, plus a `[tool.trapyze]` section with `name`, `description`, `version`, and one
  `[[tool.trapyze.settings]]` entry per option the user may change (`key`, `label`, `type` = text, int,
  float, bool, choice, date, file or folder, `default`, and `min`/`max`/`options` where they apply).
- In the code: `import trapyze_helper as tz`; read options with `tz.settings()`; report progress with
  `tz.progress(fraction, "what it's doing in plain words")`; save results with `tz.output_path(name)`;
  shared data files go in `tz.data_path(name)` and are listed as `writes = [...]` in the label.
- Never use `input()`. Never hard-code paths or keys. Keys come from the vault: list the connection
  name under `connections = [...]` in the label and read it from `os.environ`, or call a web service
  with `tz.api(name, path, params={...})`, which adds the key.
- Values shown as •••• were masked by traPYze because they are secret. Never invent them; read them
  from the environment instead.
"""
CODE_RULE = """
If the script needs to change: first list what you changed in at most five short bullet points, then
give the COMPLETE new script in one ```python block. Keep everything that already works, keep the label
valid, and change nothing that wasn't asked for."""


NEW_RULE = """
Write a new tool as ONE Python file. First say in two or three sentences what it does and what the
user must set up (for example a key under Connections), then give the COMPLETE script in one
```python block. Use only packages that are really needed and list every one under `dependencies`.
Put a clear `name` and `description` in the label, and choose an `icon` (one of: chart, table, mail,
cloud, coin, trend, archive, bell, globe, photo, gauge, target, rocket, heart, cube, database) and a
`color` (one of: blue, teal, purple, orange, rose, slate)."""


def write_prompt() -> str:
    """The text to paste into any AI chat, before describing the tool you want."""
    return (RULES + NEW_RULE).strip() + "\n\nThe tool I want:"


def build_new(description: str) -> dict[str, Any]:
    description = str(description or "").strip()
    if len(description) < 8:
        raise AIError("Describe in a sentence or two what the tool should do.")
    if len(description) > 6000:
        raise AIError("That description is very long. Keep it to the main points.")
    system = RULES + NEW_RULE
    return {"system": system, "user": "The tool I want:\n" + description, "text": write_prompt() + "\n" + description, "masked": 0}


def check_new(code: str, scratch: Path) -> tuple[Any, list[str]]:
    """(the tool as read from its label, or None; plain-English problems) for a script that isn't saved yet."""
    problems = []
    try:
        compile(code, "new_tool.py", "exec")
    except SyntaxError as exc:
        problems.append(f"Python can't read it (line {exc.lineno}: {exc.msg}). Ask the AI to fix that line.")
    scratch.mkdir(parents=True, exist_ok=True)
    tmp = scratch / "new_tool.py"
    tmp.write_text(code, encoding="utf-8")
    tool = None
    try:
        tool = read_tool(tmp)
    except LabelError as exc:
        problems.append(f"Its label has a problem: {exc}")
    except (OSError, ValueError) as exc:
        problems.append(f"Its label couldn't be read: {exc}")
    if "# [tool.trapyze]" not in code:
        problems.append("It has no traPYze label, so it would get no settings window. Ask the AI to add the label.")
    return tool, problems


class AIError(Exception):
    """A plain-English problem with the AI service."""


class AISettings:
    def __init__(self, internal: Path):
        self.path = internal / "ai.json"

    def get(self) -> dict[str, Any]:
        data = {"chat_site": "copilot", "provider": "", "model": "", "connection": ""}
        stored = _read(self.path, {})
        if isinstance(stored, dict):
            data.update({k: v for k, v in stored.items() if k in data})
        return data

    def update(self, **changes: Any) -> dict[str, Any]:
        data = self.get()
        if "chat_site" in changes and changes["chat_site"] not in CHAT_SITES:
            raise AIError("Unknown chat site.")
        if changes.get("provider") and changes["provider"] not in PROVIDERS:
            raise AIError("Unknown AI service.")
        data.update({k: str(v or "") for k, v in changes.items() if k in data})
        _write(self.path, data)
        return data


# Masking ----------------------------------------------------------------------
def mask(text: str, secrets: list[str]) -> tuple[str, int]:
    """Text with vault values and anything that looks like a key replaced by ••••."""
    count = 0
    for value in sorted({s for s in secrets if s and len(s) >= 4}, key=len, reverse=True):
        if value in text:
            count += text.count(value)
            text = text.replace(value, MASK)
    for rx, _ in SECRET_PATTERNS:
        text, n = rx.subn(MASK, text)
        count += n

    def hide(m: re.Match) -> str:
        nonlocal count
        if PLACEHOLDER.match(m.group(3)) or m.group(3) == MASK:
            return m.group(0)
        count += 1
        return m.group(0).replace(m.group(3), MASK)
    for rx in (SECRET_NAME, KEY_NAME):
        text = rx.sub(hide, text)
    return text, count


# Prompts ----------------------------------------------------------------------
def build(task: str, tool: Any, source: str, request: str = "", run: dict[str, Any] | None = None,
          log: str = "", secrets: list[str] | None = None) -> dict[str, Any]:
    """The question for the AI: {"system", "user", "text" (both together, for pasting), "masked"}."""
    if task not in TASKS:
        raise AIError("Unknown kind of help.")
    if len(source) > MAX_SCRIPT:
        raise AIError("This script is too long to send in one go.")
    script, masked = mask(source, secrets or [])
    parts = [f"Tool: {tool.name} ({tool.path.name})"]
    if task == "explain":
        ask = ("Explain what this script does, step by step: what it needs (settings, data files, connections, "
               "packages), what it produces, and anything risky or surprising. Don't change the code.")
    elif task == "why":
        if not run:
            raise AIError("Pick a run that went wrong first.")
        log_text, n = mask(log or "", secrets or [])
        settings_text, m = mask(json.dumps(run.get("settings", {}), indent=1), secrets or [])
        masked += n + m
        parts.append(f"The run of {run.get('started', '?')} ended with status '{run.get('status')}'"
                     + (f" (exit code {run.get('exit_code')})" if run.get("exit_code") is not None else "") + ".")
        if run.get("cause"):
            parts.append(f"traPYze's own explanation: {run['cause']} {run.get('action', '')}".strip())
        parts.append(f"Settings used:\n{settings_text}")
        parts.append(f"The last lines of its log:\n```\n{log_text[-12000:]}\n```")
        ask = ("Explain in plain words why it failed and what to do about it. If it is something outside the "
               "script (a missing file, a key, the internet), say what to do in traPYze or on the computer.")
    elif task == "ready":
        ask = ("Make this script a proper traPYze tool. Add or complete the label at the top: name, description, "
               "dependencies for every package it imports, and a setting for every value a user would want to "
               "change. Replace input() and hard-coded options with tz.settings(), and add tz.progress() at the "
               "main steps. Keep the calculations exactly as they are.")
    else:
        request = " ".join(str(request or "").split())
        if not request:
            raise AIError("Say what should change.")
        ask = f"Change the script as follows: {request}"
    user = "\n\n".join([ask, *parts, f"The script:\n```python\n{script}\n```"])
    system = RULES + (CODE_RULE if task in CHANGES_CODE else "\nDon't rewrite the script; just explain.")
    text = f"{system.strip()}\n\n---\n\n{user}"
    return {"system": system, "user": user, "text": text, "masked": masked}


# Answers ----------------------------------------------------------------------
FENCE = re.compile(r"```(?:python|py)?[ \t]*\r?\n(.*?)```", re.S)


def extract_code(answer: str) -> str | None:
    blocks = [b for b in FENCE.findall(answer or "") if b.strip()]
    if not blocks:
        return None
    code = max(blocks, key=len)
    return code if code.endswith("\n") else code + "\n"


def check_proposal(code: str, tool: Any, scratch: Path) -> list[str]:
    """Plain-English problems with a proposed script; empty when it's fine to use."""
    problems = []
    try:
        compile(code, tool.path.name, "exec")
    except SyntaxError as exc:
        problems.append(f"Python can't read it (line {exc.lineno}: {exc.msg}). Ask again, or fix it after saving.")
    scratch.mkdir(parents=True, exist_ok=True)
    tmp = scratch / tool.path.name
    tmp.write_text(code, encoding="utf-8")
    try:
        read_tool(tmp)
    except LabelError as exc:
        problems.append(f"Its label has a problem: {exc}")
    except (OSError, ValueError) as exc:
        problems.append(f"Its label couldn't be read: {exc}")
    finally:
        tmp.unlink(missing_ok=True)
    if MASK in code:
        problems.append("It has •••• where a secret was. Move that key to the vault first (the health check shows "
                        "where), or put the real value back yourself after saving.")
    return problems


# Calling a service -----------------------------------------------------------
def _request(url: str, headers: dict[str, str], body: dict | None, timeout: float, opener: Callable | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "User-Agent": "traPYze", **headers},
                                 method="POST" if body is not None else "GET")
    try:
        with (opener or urllib.request.urlopen)(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            payload = json.loads(exc.read().decode("utf-8", "replace"))
            err = payload.get("error", payload)
            detail = (err.get("message") if isinstance(err, dict) else str(err)) or ""
        except (ValueError, AttributeError):
            pass
        raise AIError(_plain(exc.code, detail)) from None
    except urllib.error.URLError as exc:
        raise AIError(f"Couldn't reach the AI service ({exc.reason}). Check the internet connection.") from None
    except TimeoutError:
        raise AIError("The AI service took too long to answer. Try again, or pick a faster model.") from None


def _plain(status: int, detail: str) -> str:
    short = detail[:240]
    if status in (401, 403):
        return f"The AI service refused the key. Check it, or make a new one. ({short})"
    if status == 402:
        return "The AI service wants credit on the account before it answers."
    if status == 404:
        return f"The AI service doesn't know that model. Pick another one under Look and feel, AI help. ({short})"
    if status == 429:
        return "The limit for now is reached (free use has limits per minute and per day). Try again later, or pick another model."
    if status >= 500:
        return "The AI service has a problem on its side. Try again in a minute."
    return f"The AI service said no ({status}): {short}"


def _headers(provider: str, key: str) -> dict[str, str]:
    if PROVIDERS[provider]["api"] == "anthropic":
        return {"x-api-key": key, "anthropic-version": "2023-06-01"}
    headers = {"Authorization": f"Bearer {key}"}
    if provider == "openrouter":
        headers.update({"HTTP-Referer": "https://github.com/trapyze/trapyze", "X-Title": "traPYze"})
    return headers


def models(provider: str, key: str, opener: Callable | None = None) -> list[str]:
    data = _request(PROVIDERS[provider]["base"] + "/models", _headers(provider, key), None, 30, opener)
    ids = [str(m.get("id", "")).removeprefix("models/") for m in data.get("data", []) if m.get("id")]
    skip = re.compile(r"embed|tts|audio|image|vision-only|whisper|dall|moderation|realtime|transcribe|search|veo|imagen|live", re.I)
    return sorted({i for i in ids if not skip.search(i)})


def _version(model_id: str) -> tuple:
    return tuple(int(n) for n in re.findall(r"\d+", model_id)[:3])


def pick_model(provider: str, ids: list[str]) -> str:
    """A sensible default from the provider's current list (names change too often to fix them here)."""
    if not ids:
        return ""
    if provider == "openrouter":
        return "openrouter/free" if "openrouter/free" in ids else next((i for i in ids if i.endswith(":free")), ids[0])
    if provider == "gemini":
        flash = [i for i in ids if "flash" in i and not re.search(r"lite|preview|exp|thinking", i)] or [i for i in ids if "flash" in i]
        return max(flash or ids, key=lambda i: (_version(i), "latest" not in i))
    if provider == "anthropic":
        sonnet = [i for i in ids if "sonnet" in i] or ids
        return max(sonnet, key=_version)
    if "chat-latest" in ids:
        return "chat-latest"
    gpt = [i for i in ids if i.startswith("gpt-") and not re.search(r"nano|instruct|-0\d{3}|preview", i)] or ids
    return max(gpt, key=lambda i: (_version(i), "mini" not in i))


def ask(provider: str, key: str, model: str, system: str, user: str, timeout: float = 180,
        opener: Callable | None = None) -> str:
    if provider not in PROVIDERS:
        raise AIError("Choose an AI service first, under Look and feel, AI help.")
    if not model:
        raise AIError("Choose a model first, under Look and feel, AI help.")
    p = PROVIDERS[provider]
    if p["api"] == "anthropic":
        data = _request(p["base"] + "/messages", _headers(provider, key),
                        {"model": model, "max_tokens": 16000, "system": system, "messages": [{"role": "user", "content": user}]},
                        timeout, opener)
        text = "".join(part.get("text", "") for part in data.get("content", []) if part.get("type") == "text")
    else:
        data = _request(p["base"] + "/chat/completions", _headers(provider, key),
                        {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
                        timeout, opener)
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise AIError("The AI service sent an answer traPYze couldn't read.") from None
    if not text.strip():
        raise AIError("The AI service sent an empty answer. Try again, or pick another model.")
    return text


_busy = threading.Semaphore(2)  # at most two questions at once
