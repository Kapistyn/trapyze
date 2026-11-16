# Changelog

What changed in each version of traPYze. The newest is at the top.

## [0.15.0] - 2026-11-16

**Ready-made tools.**

- **Get tools** on the Tools screen: three packs that come with traPYze and are
  added with one click. All eleven tools work without the internet and use only
  what comes with Python, so there is nothing to install.
  - **Everyday files**: tidy a folder, find duplicate files, back up a folder,
    rename files, and see what takes the space.
  - **Home finance**: a monthly overview by category from your bank's CSV export
    (it finds the columns itself, for most banks), and a subscription finder.
  - **Tables and data**: check a downloaded CSV, merge CSV files, put a CSV into
    a database, and get a database table back out for Excel.
- Tools that change files show a list first, and never delete or overwrite your
  files. Every pack tool is run on sample data on Windows, Mac and Linux for
  every change to traPYze.

## [0.14.0] - 2026-11-16

**AI-written tools, and a safer first run.**

- **Have an AI write a tool.** *New tool*, then "Or have an AI write it": describe
  what you want, and traPYze hands the AI its rules together with your description,
  by copy and paste with any chat site or with your own key. It checks the answer,
  shows what the script can do, and puts the tool on the New shelf. "Copy only the
  prompt" gives you the bare prompt for a chat of your own.
- **A look before the first run.** A tool you imported or that an AI wrote shows
  where it came from, what it can do (the internet, vault keys, deleting files,
  starting programs) and what the health check found, before it runs for the first
  time. Until then it can't be planned or chained.
- **Updates are verified.** Each release now publishes checksums, and traPYze
  compares the downloaded update with them before installing. A file that doesn't
  match is never installed.
- One set of rules for AI: the prompt in the guide, the new `AGENTS.md` for coding
  assistants and what the app sends are the same text, checked by a test.

## [0.13.2] - 2026-11-15

- The Windows installer no longer stops at the very end with a red
  "NativeCommandError" in Windows PowerShell 5.1, when uv merely notes that its
  folder is already in the PATH. traPYze was installed; the shortcuts weren't made.
- Every change now runs the real installers on GitHub's Windows (PowerShell 5.1),
  Mac and Linux machines, twice: a first install and an update.

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
