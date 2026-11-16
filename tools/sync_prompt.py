"""Put the prompt traPYze uses for AI-written tools into docs/guide.md and AGENTS.md.

Run after changing RULES or NEW_RULE in src/trapyze/ai.py:  python tools/sync_prompt.py
A test fails when the documents and the app disagree.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trapyze.ai import write_prompt  # noqa: E402

START, END = "<!-- prompt:start -->", "<!-- prompt:end -->"

for name in ("docs/guide.md", "AGENTS.md"):
    path = ROOT / name
    text = path.read_text(encoding="utf-8")
    head, rest = text.split(START, 1)
    tail = rest.split(END, 1)[1]
    path.write_text(f"{head}{START}\n````text\n{write_prompt()}\n````\n{END}{tail}", encoding="utf-8")
    print("updated", name)
