#!/bin/sh
# Removes traPYze from macOS or Linux. Your home folder (tools, results, vault) stays.
set -u
UV=$(command -v uv || { [ -x "$HOME/.local/bin/uv" ] && echo "$HOME/.local/bin/uv"; } || true)
BIN=$([ -n "$UV" ] && "$UV" tool dir --bin || echo "$HOME/.local/bin")
pkill -f "trapyze.desktop|bin/trapyze" 2>/dev/null || true
[ -x "$BIN/trapyze" ] && "$BIN/trapyze" schedule remove-all
rm -rf "$HOME/Applications/traPYze.app" "$HOME/.local/share/applications/trapyze.desktop" "$HOME/Desktop/trapyze.desktop"
[ -n "$UV" ] && "$UV" tool uninstall trapyze
printf '\n  traPYze is removed. Your tools, results and vault are still in %s/Trapyze;\n' "$HOME"
printf '  delete that folder yourself if you no longer need them. uv stays installed.\n\n'
