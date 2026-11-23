# Changelog

What changed in each version of traPYze. The newest is at the top.

## [0.22.3] - 2026-11-23

- The README and the guide describe what came in the last versions: the Storage screen
  and the bin, the package library, updating a program from outside, tries after a failure,
  steps that ask first, the Git backup, removing runs and the Keep button.

## [0.22.2] - 2026-11-23

- **No more "Add market_core" for files that sit in a neighbouring program.** A tool that
  reaches into another program on purpose (the maps use `market_core` from the market
  database) was told that `market_core` was a missing package. Adding it to the package
  list made the run stop with "The packages this tool asks for don't fit together".
  Files of other programs are now recognised as yours, not as packages.

## [0.22.1] - 2026-11-22

- **Remove runs from the Outputs list.** Every run has a "Remove" button, and when the list
  shows failed runs there is a button to remove all of them at once. Removed runs go to the
  bin for 30 days, and the message afterwards has an Undo. Runs that are still running are
  left alone.

## [0.22.0] - 2026-11-22

- **Ask me first, in a chain.** Each step of a chain has a box "Ask me first". The chain
  stops there, you get a notification, and the chain window shows "Run <tool>" or "Skip this
  step". If nobody answers within an hour, the chain stops at that step.
- **Back up scripts.** More, "Back up scripts…" keeps every tool and program in a Git
  history, and can send a copy to your own (private) repository. Only code and notes go in:
  never keys, data or results, and a script that contains a private key is held back. Back up
  now, or once a day when no tool is running. Needs Git installed; traPYze never sees the
  password for the repository.

## [0.21.0] - 2026-11-22

- **Plans can try again after a failure.** In a plan: "If it fails: Tell me / Try once more /
  twice / 3 times", with the minutes to wait between tries (10 by default). For a tool, the
  tool runs again; for a chain, the step that failed runs again and the rest carries on.
  The plan's history shows "Trying again in 10 min (try 2 of 3)" while it waits. You get the
  notification only when the last try has failed.

## [0.20.2] - 2026-11-22

- **Update a program from a file or folder.** A script you changed outside traPYze
  (with your AI, say) can now replace the one in its program: tile menu, "Update from a
  file or folder…", or in Scripts and folders. traPYze lists what is new, changed or the
  same, and copies the ones you tick. A script that comes without a label keeps the old
  tile, name, settings, connections and packages. What was replaced is kept in
  `scripts/_replaced`.

## [0.20.1] - 2026-11-22

- **A Keep button on results, as an option.** Look and feel has a new switch,
  "Show a Keep button on results" (off by default). When it is on, every result in
  the history and in the result window has a Keep / Kept button. A kept run stays
  out of the automatic tidy-up. Runs can always be ticked in Storage as well.

## [0.20.0] - 2026-11-22

- **Storage, and an automatic tidy-up.** Under the top ⋯ menu, "Storage…" shows
  what takes room: results, run logs, shared data, the bin, old versions and the
  package cache, then every tool with its size (click it for its runs). Old
  results and run logs are put in the bin once a day: older than 30 days, but the
  newest 5 runs of each tool always stay, and a run you tick as "Keep this run" is
  never touched. Days and the number of runs can be changed, also per tool.
  "Tidy up now" does it at once and says first what it would move. Everything
  goes to the bin for 30 days and can be put back from "Recently removed".
  Your data folder is measured but never tidied. Also: Empty the bin now (asks
  twice) and Clean the package cache.

## [0.19.1] - 2026-11-22

- **Importing starts in your Downloads folder.** The Folder… and File… buttons of
  the import window (and Browse… for a .env file) open in Downloads, where a
  downloaded script lands, instead of the traPYze folder. After you've chosen
  something, they open in its folder. A Downloads folder moved by Windows is found.

## [0.19.0] - 2026-11-22

- **Key files in the vault.** A new kind of connection, "Key file (SSH key,
  certificate)": choose the file (or paste its text) and traPYze keeps it
  encrypted with your other keys, so the original can be deleted. A public key
  or anything that isn't a key is refused with a plain message. Tools get the
  text in a variable (`ORACLE_KEY` for a connection called `oracle`), and the
  helper has `tz.key_text("oracle")` and `tz.key_file("oracle")`, the second
  one a temporary file that is deleted when the run ends.

## [0.18.0] - 2026-11-22

- **Package library.** Under the top ⋯ menu, "Package library…" shows every
  package of every tool in one list: which versions are in use and by how many
  tools, which tool asks for what, and where a newer version exists. Several
  versions of one package live side by side; each tool keeps its own. A tool that
  asks for an exact version or an upper limit (`==1.5.3`, `<2`) keeps it.
- **Update everything that passes its test.** One button runs the tested update
  for every tool with pinned versions, one after the other. A tool that is
  running is left alone, one whose test fails keeps its old versions, and the
  result per tool is shown. "Look for newer versions" checks without changing.
- **Common packages.** A list of the packages almost every tool uses (pandas,
  numpy, requests, yfinance, scipy, matplotlib, pyarrow, lxml, openpyxl,
  scikit-learn, editable), downloaded once into the library with one button, so
  a tool's first run doesn't wait for them. The files are stored once, however
  many tools use them.

## [0.17.10] - 2026-11-22

- **Packages used through a helper file now count.** A script that imports a
  sibling file (`import rotation401k`) also needs what that file imports, such as
  yfinance. "Give it a tile" now puts those packages in the new label, and the
  Health check names a missing one ("It imports yfinance, which isn't in its
  package list") with an "Add yfinance" button.

## [0.17.9] - 2026-11-22

- **Scripts and folders.** Under the top ⋯ menu, "Scripts and folders…" lists
  everything in the scripts folder: single scripts and each program with its
  files, and what each one is (has a tile, tile hidden, or a helper without a
  tile). Each row has Open (the file) and each program has Open folder. A helper
  that can run on its own gets **Give it a tile**: traPYze adds the label for you
  (name, options and packages read from the script). A program's tile menu has
  "Scripts in this program…", which opens the same list at that program.

## [0.17.8] - 2026-11-21

- **Remove, from a tile's menu.** A tool's ⋯ menu now ends with "Remove…" (for a
  tool in a program: "Remove the program…", all its scripts together). Nothing is
  deleted at once: it goes into a bin for 30 days. **More, Recently removed…**
  lists what's there, with "Put back". A chain's menu has "Delete…" too.
  A running tool can't be removed, and planned runs wait until you put it back.

## [0.17.7] - 2026-11-21

- **Shared data takes up one line instead of a row of chips.** The main page shows
  "Shared data · 14 files · newest today 09:12" (and how many tools need fresher
  data). Click it for the full list: search, sort by newest, name or size, with
  old files marked. Tools still show "Data needs updating" on their own tiles.

## [0.17.6] - 2026-11-20

- **The .env import takes the keys it doesn't know too.** Variables that match no
  service become connections of their own, grouped by name: everything starting
  with `TELEGRAM_` in one connection, `EMAIL_` and `SMTP_` in one, a single key
  such as `TAVILY_API_KEY` in `tavily`. Tools use them by that name. Keys that
  look secret are stored as secret; placeholders like `YOUR_API_KEY` are left out.

## [0.17.5] - 2026-11-20

- **One .env file for all your keys.** In Connections, "Import a .env file" has a
  new button, "Sort keys into services". traPYze recognises the variable names of
  the services it knows (HF Data Library, Tiingo, FMP, Alpha Vantage, Twelve Data,
  Finnhub, EODHD, Massive, GitHub), shows only the names, and puts each key into
  the connection with the service's name, with its limits and "Use with
  tz.api()" already on. A key that changed replaces the stored one; the others
  stay as they are. Variables it doesn't know are listed, not imported.

## [0.17.4] - 2026-11-19

- **traPYze has a website**: <https://kapistyn.github.io/trapyze/>, with the
  guide and this changelog.
- **traPYze is on PyPI.** With uv already installed: `uv tool install
  "trapyze[desktop]"`, then `trapyze shortcut`.

## [0.17.3] - 2026-11-19

- **The window fills the screen when it opens**, so the bottom is no longer cut
  off on smaller or scaled screens. Under Look and feel, *When the window opens*:
  fill the screen, full screen (no title bar) or normal size. A normal window is
  now kept smaller than the screen. **F11** switches full screen on and off.

## [0.17.2] - 2026-11-19

- Opening traPYze now looks for a new version straight away (unless it looked in
  the last hour), instead of waiting until a day has passed since the last look.

## [0.17.1] - 2026-11-19

- **The version is always in view**, at the bottom of the menu: "traPYze 0.17.1,
  Up to date", or in orange "0.17.2 is ready to install". Click it to look for a
  new version straight away, or to see what's new when there is one.

## [0.17.0] - 2026-11-19

- **Shared prices for all tools: `tz.prices()`.** A tool asks for the bars it
  needs (`tz.prices("SPY", start="2010-01-01")`) and gets a pandas table. One
  copy is kept in `data/trapyze_prices.sqlite` for every tool, and only what's
  missing is downloaded, so ten tools asking for the same ticker in a day cost
  one small download. Dividends and splits are picked up and the older bars
  rescaled; intraday bars are kept for good, so their history grows past
  Yahoo's limits; without internet the saved prices are used. Bars from a
  broker can be stored next to Yahoo's with `tz.save_prices()`.
- Tools written with *Have an AI write it* now use `tz.prices()` for prices.

## [0.16.0] - 2026-11-19

- **Reminders for keys that run out.** On a connection card you can say the key
  runs out every so many days. From 5 days before, the card, the home screen and
  a notification tell you, until you paste the new key. The count starts on the
  day you last saved the key; changing a note or a limit doesn't restart it. It
  works while the vault is locked too (only names and dates are kept outside it).
  HF Data Library connections get 30 days by themselves, also ones made earlier.
- HF Data Library's preset now allows 100 downloads a minute, its real limit.
- A plan that runs once tomorrow now reads "Once, tomorrow at 09:00", not
  "Once, on tomorrow at 09:00".

## [0.15.3] - 2026-11-16

- **Tiingo, HF Data Library and GitHub** are known services under Connections.
  Name a connection `tiingo`, `hfdata` or `github`, paste the key, and the web
  address, where the key goes and the limits fill themselves in. Before, their
  settings were behind the *Use with tz.api()* switch and had to be typed by hand.

## [0.15.2] - 2026-11-16

- **Updating from inside traPYze works again on Windows.** Before, traPYze could
  close for the update and then nothing happened: the update didn't run, and
  traPYze didn't open again. The updater is now a small Python helper instead of a
  hidden PowerShell script, and traPYze only closes once the helper reports that
  it's running. If it doesn't, traPYze stays open and says so.
- The update notice asks GitHub again before installing, and when it's opened
  more than an hour after the last look. So on a day with several releases it no
  longer offers an older one.

## [0.15.1] - 2026-11-16

- Two tools that complete the Everyday files pack: **Set duplicates aside** moves
  the extra copies of identical files to a folder you can check (nothing is
  deleted), and **Restore a backup** checks a backup zip and unpacks it into a
  new folder, never over your current files. If you added the pack before, *Get
  tools* offers "Add the missing tools".

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
