# Changelog

What changed in each version of traPYze. The newest is at the top.

## [0.13.1] - 2026-11-15

- The Windows installer now always uses the official uv. Before, it could borrow a
  copy of uv that another program brought along (an AI agent, an editor); on some
  computers that stopped the install with "os error 448".
- traPYze itself also prefers the official uv over such copies when running tools.
- The installer says so when it runs as administrator, and explains error 448 in
  plain words if Windows still blocks the install.

## [0.13.0] - 2026-11-15

**traPYze gets a home online.**

- Installers: **traPYze-Setup.exe** for Windows, or one line in PowerShell
  (`install.ps1`) or a Mac or Linux terminal (`install.sh`). They install uv if
  needed, then traPYze with its own window, add a shortcut and open it. No
  administrator needed.
- traPYze **updates itself**: it looks for a new release once a day, offers it
  on the Tools screen, and installs it in the background, opening again when
  it's done. Also `trapyze update` and `trapyze version`.
- On a Mac, `trapyze shortcut` puts **traPYze.app** in your Applications.
- Uninstall scripts that also take your plans out of the computer's scheduler
  (`trapyze schedule remove-all`) and leave your traPYze folder alone.
- The project on GitHub: tests on Windows, macOS and Linux for every change, and
  releases built automatically from a tag.
- Fixed on Windows: traPYze now takes its port for itself, so a second program (or
  a second traPYze) can't end up answering in its place.
- Fixed on Windows: looking for WSL folders no longer fails when WSL isn't set up.
- Fixed: a newly made vault could lock itself at the next click on a computer that
  had been on for a while.
- Fixed on Mac and Windows: importing recognises traPYze's own folder also through
  symlinks and short folder names.

## [0.12.0] - 2026-11-15

**Ask AI.**

- Explain a script, say why a run failed, make it traPYze-ready, or change it.
- By copy and paste with Copilot, Gemini, Google AI Mode, ChatGPT or Claude (free,
  no setup), or built in with a Gemini, OpenRouter, Anthropic or OpenAI key kept
  in the vault.
- Keys and passwords are masked before anything is sent; a changed script is
  shown as differences and only saved when you say so.

## [0.11.0] - 2026-11-15

- **Edit** a tool in your own editor (VS Code, PyCharm, Notepad++ and others).
- **Changes**: a copy of every version of a script, with going back in one click.
- **Health check**: an offline review with a traffic light and fixes.
- **New tool** from five templates; an **Apps** shelf for programs with their own
  window.

## [0.10.0] - 2026-11-15

- The Tools screen becomes a **desktop**: small tiles on shelves sorted by what
  tools do, drag and drop, Favourites, a New shelf, topic chips, a Today strip,
  quick run, and Desktop, Cards and List views.

## [0.9.0] - [0.9.2]

- Package versions pinned per tool, a daily look for newer ones, updates tested
  before use, and going back. Sharing a tool as one .py or .zip.
- Programs with several files show only their main script; helpers are hidden.

## [0.8.0] - [0.8.1]

- The import wizard for single scripts and whole program folders, also from WSL
  and .zip files, with Tidy up.

## Earlier

- 0.7: plans that run by themselves through Task Scheduler, cron or launchd.
- 0.6: its own window with a tray icon, notifications and shortcuts.
- 0.5: presets, chains, data-freshness checks and Look and feel.
- 0.4: the vault and the gateway for web services (`tz.api()`).
- 0.1 – 0.3: the core: labels, settings, the runner, history and the window.
