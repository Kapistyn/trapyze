#!/bin/sh
# traPYze installer for macOS and Linux. Paste this into a terminal:
#   curl -LsSf https://github.com/kapistyn/trapyze/releases/latest/download/install.sh | sh
#
# What it does, all inside your own user account:
#   1. installs uv (by Astral), which fetches and runs Python for traPYze, if it isn't there yet
#   2. installs the newest traPYze from its GitHub releases, with its own window and tray icon
#   3. adds traPYze to your apps (Applications on a Mac, the app menu on Linux) and opens it
# Running it again updates traPYze. Your tools, results, plans and vault are never touched.
set -eu
REPO="kapistyn/trapyze"

say() { printf '  %s\n' "$1"; }
fail() { printf '\n  %s\n  Nothing else was changed. Questions: https://github.com/%s/issues\n\n' "$1" "$REPO" >&2; exit 1; }

printf '\n  traPYze installer\n\n'

# 1. uv
if command -v uv >/dev/null 2>&1; then
    UV=$(command -v uv)
else
    say "Installing uv, which runs Python for traPYze (about 30 MB)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh || fail "uv couldn't be installed."
    for c in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv"; do [ -x "$c" ] && UV="$c" && break; done
    [ -n "${UV:-}" ] || fail "uv was installed but can't be found. Open a new terminal and try again."
fi
say "Using uv at $UV"

# 2. The newest release
SOURCE="${TRAPYZE_WHEEL:-}"   # set this to a local .whl file to install a build of your own
if [ -z "$SOURCE" ]; then
    JSON=$(curl -LsSf -H "User-Agent: traPYze-installer" "https://api.github.com/repos/$REPO/releases/latest") \
        || fail "Couldn't ask GitHub for the newest version. Check the internet connection."
    SOURCE=$(printf '%s' "$JSON" | grep -o '"browser_download_url": *"[^"]*\.whl"' | head -n 1 | sed 's/.*"\(https[^"]*\)"/\1/')
    [ -n "$SOURCE" ] || fail "The newest release has no file to install."
    say "Newest version: $(printf '%s' "$JSON" | grep -o '"tag_name": *"[^"]*"' | head -n 1 | sed 's/.*"\([^"]*\)"$/\1/')"
fi

# 3. Install (a traPYze that is open keeps running the old version until it's closed)
say "Installing traPYze (the first time takes a minute or two)..."
if [ "$(uname)" = "Linux" ]; then
    say "On Linux traPYze opens in your web browser (its own window needs extra system parts)."
fi
"$UV" tool install --reinstall --python 3.12 "trapyze[desktop] @ $SOURCE" || fail "Installing traPYze didn't work; the lines above say why."
"$UV" tool update-shell >/dev/null 2>&1 || true
BIN=$("$UV" tool dir --bin)
[ -x "$BIN/trapyze" ] || fail "traPYze was installed but can't be found in $BIN."

# 4. Add it to the apps, then open it
"$BIN/trapyze" shortcut || true
printf '\n  Done. traPYze is opening. Your tools live in %s/Trapyze\n\n' "$HOME"
nohup "$BIN/trapyze-app" >/dev/null 2>&1 &
