"""The traPYze command line. The desktop app will call the same functions.

    trapyze open                 open traPYze in your browser
    trapyze init                 create the home folder with example tools
    trapyze usage                today's web-service calls through tz.api()
    trapyze list                 show your tools
    trapyze show TOOL            show a tool's settings and defaults
    trapyze run TOOL [--set key=value ...]
    trapyze check                check every tool's label and the engine
    trapyze history [TOOL]       recent runs
"""

from __future__ import annotations

import argparse
import subprocess
import json
import sys
import time
from typing import Any

from . import __version__
from .home import Home
from .label import LabelError, SettingError, Tool
from .locks import Busy
from .runner import EngineMissing, Event, Run, find_engine, history
from .vault import VaultError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="trapyze", description="Run your Python tools without the technical bits.")
    parser.add_argument("--home", help="the traPYze home folder (default: ~/Trapyze or $TRAPYZE_HOME)")
    parser.add_argument("--version", action="version", version=f"traPYze {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="create the home folder")
    p.add_argument("--no-examples", action="store_true", help="don't add the example tools")
    sub.add_parser("list", help="show your tools")
    p = sub.add_parser("show", help="show a tool's settings")
    p.add_argument("tool")
    p = sub.add_parser("run", help="run a tool")
    p.add_argument("tool")
    p.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="change a setting")
    p.add_argument("--preset", help="start from a saved preset")
    p.add_argument("--quiet", action="store_true", help="hide the tool's own output")
    p = sub.add_parser("chain", help="list chains, or run one")
    p.add_argument("action", choices=["list", "run"])
    p.add_argument("name", nargs="?")
    p.add_argument("--quiet", action="store_true", help="hide the tools' own output")
    p = sub.add_parser("open", help="open traPYze (its own window, or your browser)")
    p.add_argument("--port", type=int, default=0, help="use this port (default: the first free one from 8765)")
    p.add_argument("--no-browser", action="store_true", help="don't open the browser, just print the address")
    how = p.add_mutually_exclusive_group()
    how.add_argument("--window", action="store_true", help="in its own window (needs the desktop add-on)")
    how.add_argument("--browser", action="store_true", help="in your browser")
    sub.add_parser("shortcut", help="put a traPYze shortcut on the desktop and in the Start menu")
    p = sub.add_parser("schedule", help="list plans, or bring the computer's scheduler up to date")
    p.add_argument("action", choices=["list", "sync", "remove-all"], nargs="?", default="list",
                   help="remove-all takes every plan out of the computer's scheduler (used when uninstalling)")
    p = sub.add_parser("fire", help=argparse.SUPPRESS)  # started by the computer's scheduler
    p.add_argument("plan")
    p.add_argument("--now", action="store_true", help="run it now, whatever the time")
    sub.add_parser("check", help="check every tool's label and the engine")
    p = sub.add_parser("history", help="recent runs")
    p.add_argument("tool", nargs="?")

    sub.add_parser("usage", help="today's web-service calls through tz.api()")
    sub.add_parser("version", help="which traPYze this is, and whether a newer one is out")
    p = sub.add_parser("update", help="install the newest traPYze from its home online")
    p.add_argument("--check", action="store_true", help="only say whether there's a newer version")

    args = parser.parse_args(argv)
    home = Home(args.home)
    if args.command in ("version", "update"):
        return _update(home, args.command == "version" or args.check, strict=args.command == "update")

    try:
        if args.command == "init":
            return _init(home, not args.no_examples)
        if not home.exists():
            if args.command in ("open", "shortcut"):  # first start (or the installer): just set everything up
                home.init(with_examples=True)
                print(f"Created your traPYze home at {home.root}")
            else:
                print(f"There's no traPYze home at {home.root} yet. Create it with: trapyze init")
                return 1
        else:
            home.init(with_examples=False)  # brings the shared helper up to this version
        if args.command == "usage":
            return _usage(home)
        if args.command == "list":
            return _list(home)
        if args.command == "show":
            return _show(home.find(args.tool))
        if args.command == "run":
            return _run(home, home.find(args.tool), args.set, args.quiet, args.preset)
        if args.command == "chain":
            return _chain(home, args.action, args.name, args.quiet)
        if args.command == "open":
            from .desktop import open_app

            mode = "window" if args.window else "browser" if (args.browser or args.no_browser) else "auto"
            return open_app(home, mode, args.port, console=True, open_browser=not args.no_browser)
        if args.command == "fire":
            from .schedule import fire

            return fire(home, args.plan, force=args.now)
        if args.command == "schedule":
            return _schedule(home, args.action)
        if args.command == "shortcut":
            from .desktop import make_shortcuts

            try:
                made = make_shortcuts(home)
            except (OSError, subprocess.SubprocessError) as exc:
                print(f"The shortcut couldn't be made: {exc}")
                return 1
            print("Made:\n  " + "\n  ".join(made))
            print("Double-click traPYze there to open it without a terminal.")
            return 0
        if args.command == "check":
            return _check(home)
        if args.command == "history":
            return _history(home, args.tool)
    except (LookupError, LabelError, SettingError, EngineMissing, Busy, VaultError) as exc:
        print(str(exc))
        return 1
    return 0  # pragma: no cover


def _usage(home: Home) -> int:
    from .apis import helper
    found = helper().usage(home.internal / "api.sqlite")
    if not found:
        print("No web-service calls through tz.api() today.")
        return 0
    print("Today (UTC day):")
    for name, u in sorted(found.items()):
        extra = f", {u['errors']} problems" if u["errors"] else ""
        waited = f", waited {u['waited']} s for limits" if u["waited"] else ""
        print(f"  {name}: {u['calls']} calls, {u['cached']} answered from the cache{extra}{waited}")
    return 0


def _init(home: Home, examples: bool) -> int:
    added = home.init(with_examples=examples)
    print(f"Your traPYze home is ready at {home.root}")
    for path in added:
        print(f"  added {path.relative_to(home.root)}")
    print("Put your scripts in the 'scripts' folder. Try: trapyze list")
    return 0


def _list(home: Home) -> int:
    tools, problems = home.tools()
    if not tools and not problems:
        print(f"No tools yet. Put a .py file in {home.scripts}")
        return 0
    width = max((len(t.name) for t in tools), default=0)
    for t in tools:
        print(f"  {t.name.ljust(width)}  {t.description}")
    for p in problems:
        print(f"  ! {p.path.name}: {p.message}")
    return 0


def _show(tool: Tool) -> int:
    print(tool.name)
    if tool.description:
        print(f"  {tool.description}")
    print(f"  file: {tool.path.name}   version: {tool.version}")
    if tool.dependencies:
        print(f"  needs: {', '.join(tool.dependencies)}")
    if not tool.settings:
        print("  This tool has no settings.")
        return 0
    print("  Settings (change with --set key=value):")
    for s in tool.settings:
        extra = f"  one of: {', '.join(s.options)}" if s.options else ""
        if s.min is not None or s.max is not None:
            extra += f"  range: {s.min if s.min is not None else ''}..{s.max if s.max is not None else ''}"
        if s.only_for:
            extra += "  only when " + " and ".join(f"{k} is {'/'.join(v)}" for k, v in s.only_for.items())
        print(f"    {s.key} = {_show_value(s.default)}   ({s.label}, {s.type}){extra}")
    return 0


def _run(home: Home, tool: Tool, pairs: list[str], quiet: bool, preset: str | None = None) -> int:
    chosen: dict[str, Any] = {}
    if preset:
        from .store import Presets, StoreError
        try:
            chosen.update(Presets(home.internal).get(tool.id, preset))
        except StoreError as exc:
            names = ", ".join(Presets(home.internal).for_tool(tool.id)) or "none yet"
            print(f"{exc} Presets for {tool.name}: {names}.")
            return 1
    for pair in pairs:
        if "=" not in pair:
            print(f"Write settings as key=value, for example --set top_n=25 (got '{pair}').")
            return 1
        key, value = pair.split("=", 1)
        chosen[key.strip()] = value
    env, secrets = _vault_for(home, tool)
    run = Run(home, tool, chosen, extra_env=env, secrets=secrets)
    bar = _Bar(enabled=sys.stdout.isatty())

    def on_event(event: Event) -> None:
        if event.kind == "output" and not quiet:
            bar.clear()
            print(event.line)
        elif event.kind in ("progress", "step"):
            bar.draw(run.fraction, run.step)

    print(f"Running {tool.name}… (press Ctrl+C to stop)")
    run.start(on_event)
    # Wait in short slices. On Windows a long, uninterrupted wait never sees
    # Ctrl+C, so the user couldn't stop a tool from the terminal.
    try:
        while run.running:
            run.wait(0.2)
    except KeyboardInterrupt:
        bar.clear()
        print("Stopping…")
        run.cancel()
        while run.running:
            try:
                run.wait(0.2)
            except KeyboardInterrupt:
                pass  # already stopping; a second Ctrl+C changes nothing
    result = run.result
    bar.clear()
    assert result is not None
    if result.ok:
        if result.status == "warning":
            print(f"{tool.name} finished in {_duration(result.seconds)}, with warnings worth a look.")
            print(result.action)
        else:
            print(f"Bingo! {tool.name} finished in {_duration(result.seconds)}.")
        if result.files:
            print(f"Files in {result.output_dir}:")
            for f in result.files:
                print(f"  {f}")
        return 0 if result.status == "done" else 2
    print(result.cause)
    print(result.action)
    print(f"Full log: {result.log}")
    return 1


def _update(home: Home, only_check: bool, strict: bool = True) -> int:
    from . import __version__
    from .desktop import ask_to_quit, find_running, launcher
    from .project import configured, RELEASES
    from .runner import find_engine
    from .updater import UpdateError, Updates, start_update

    print(f"traPYze {__version__}")
    if not configured():
        print("This copy was built without a home online, so it can't look for updates.")
        return 0
    updates = Updates(home.internal)
    try:
        st = updates.check()
    except UpdateError as exc:
        print(exc)
        return 1 if strict else 0  # "version" did its job: it showed the version
    latest = st["latest"]
    if not st["available"]:
        print("That's the newest version." if latest.get("version") else "No release online yet.")
        return 0
    print(f"traPYze {latest['version']} is available. What's new: {latest.get('page') or RELEASES}")
    if only_check:
        print("Install it with: trapyze update")
        return 0
    running = find_running(home)
    if running:
        if running.get("busy"):
            print("traPYze is running a tool right now. Try again when it's done.")
            return 1
        ask_to_quit(running)
        print("Closed the open traPYze window.")
    target, args = launcher()
    try:
        start_update(home.internal, find_engine(), latest["wheel"], [target, *args])
    except UpdateError as exc:
        print(exc)
        return 1
    print("Updating in the background; traPYze opens again when it's done (about a minute).")
    print(f"If it doesn't, see {updates.log}.")
    return 0


def _schedule(home: Home, action: str) -> int:
    import datetime as dt

    from .schedule import NeedsPassword, Plans, System, describe, nice_time, next_times, sync

    plans = Plans(home.internal)
    found = plans.all()
    if not found:
        print("No plans yet. Make one in the window: Schedule, then Plan a run.")
        return 0
    if action == "remove-all":
        system = System(home.root)
        for p in found:
            try:
                system.remove(p, [])
            except Exception as exc:  # keep going: this is a clean-up
                print(f"{p['name']}: {exc}")
        print(f"Took {len(found)} plan{'s' if len(found) != 1 else ''} out of the computer's scheduler. "
              "They stay in traPYze; 'trapyze schedule sync' puts them back.")
        return 0
    if action == "sync":
        system = System(home.root)
        for p in found:
            try:
                sync(plans, system, p)
            except NeedsPassword:
                print(f"{p['name']}: runs while logged out, so Windows needs your password. Save it again in the window.")
        found = plans.all()
    now = dt.datetime.now()
    for p in found:
        upcoming = next_times(p["when"], now) if p.get("enabled", True) else []
        state = "off" if not p.get("enabled", True) else (f"next {nice_time(upcoming[0], now)}" if upcoming else "nothing left to run")
        sync_state = p.get("sync") or {}
        trouble = "" if sync_state.get("ok", True) else f"  (background: {sync_state.get('message')})"
        print(f"{p['name']}: {describe(p['when'])}; {state}{trouble}")
    return 0


def _chain(home: Home, action: str, name: str | None, quiet: bool) -> int:
    from .store import ChainRun, Chains, Presets, StoreError, step_settings

    chains = Chains(home.internal)
    if action == "list" or not name:
        found = chains.all()
        if not found:
            print("No chains yet. Make one in the window: Tools, then New chain.")
            return 0
        for c in found:
            print(f"{c.name}  ({len(c.steps)} steps; {'stops' if c.on_problem == 'stop' else 'carries on'} after a problem)")
        return 0
    try:
        chain = chains.get(name)
    except StoreError as exc:
        print(exc)
        return 1
    tools = {t.id: t for t in home.tools()[0]}
    missing = [s.tool for s in chain.steps if s.tool not in tools]
    if missing:
        print(f"This chain uses tools that aren't in the scripts folder any more: {', '.join(missing)}.")
        return 1
    remembered = {}
    try:
        remembered = json.loads((home.internal / "last_settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    try:
        settings = [step_settings(s, Presets(home.internal), remembered) for s in chain.steps]
    except StoreError as exc:
        print(exc)
        return 1
    prepared = {}
    for step in chain.steps:  # ask for the PIN and permissions now, before anything runs
        if step.tool not in prepared:
            prepared[step.tool] = _vault_for(home, tools[step.tool])

    def start(tool_id: str, chosen: dict) -> Run:
        env, secrets = prepared[tool_id]
        run = Run(home, tools[tool_id], chosen, extra_env=env, secrets=secrets)

        def on_event(event: Event) -> None:
            if event.kind == "output" and not quiet:
                print("   " + event.line)
        return run.start(on_event)

    names = {t.id: t.name for t in tools.values()}
    cr = ChainRun(chain, settings, names, start).begin()
    print(f"Running the chain {chain.name} ({len(chain.steps)} steps; press Ctrl+C to stop)")
    shown: dict[int, str] = {}
    try:
        while cr.wait(0.2) == "running":
            for i, st in enumerate(cr.steps):
                if shown.get(i) != st["status"] and st["status"] != "waiting":
                    shown[i] = st["status"]
                    print(f"{i + 1}. {st['name']}: {_STEP_WORDS.get(st['status'], st['status'])}"
                          + (f" — {st['message']}" if st["message"] and st["status"] != "running" else ""))
    except KeyboardInterrupt:
        print("Stopping…")
        cr.stop()
        cr.wait()
    for i, st in enumerate(cr.steps):
        if shown.get(i) != st["status"]:
            print(f"{i + 1}. {st['name']}: {_STEP_WORDS.get(st['status'], st['status'])}"
                  + (f" — {st['message']}" if st["message"] else ""))
    print({"done": "Bingo! The whole chain finished.", "warning": "The chain finished, with warnings worth a look.",
           "stopped": "The chain was stopped.", "failed": "The chain had a problem; see the steps above."}[cr.status])
    return {"done": 0, "warning": 2}.get(cr.status, 1)


_STEP_WORDS = {"running": "running…", "done": "done", "warning": "done, with warnings", "failed": "problem",
               "stopped": "stopped", "skipped": "skipped"}


def _vault_for(home: Home, tool: Tool) -> tuple[dict[str, str], list[str]]:
    """Unlock the vault and ask permission in the terminal, when the tool needs connections."""
    if not tool.connections:
        return {}, []
    from getpass import getpass

    from .vault import NeedsPermission, NeedsUnlock, Vault, VaultError, WrongPin, secrets_for

    vault = Vault(home.internal)
    for attempt in range(3):
        try:
            return secrets_for(vault, tool.id, tool.name, tool.connections)
        except NeedsUnlock:
            if not sys.stdin.isatty():
                raise VaultError(f"{tool.name} needs the vault. Run it from traPYze's window, or in a terminal where you can type the PIN.")
            try:
                vault.unlock(getpass("Vault PIN: "))
            except WrongPin as exc:
                print(exc)
        except NeedsPermission as exc:
            if not sys.stdin.isatty():
                raise
            answer = input(f"Allow {tool.name} to use {', '.join(exc.names)}? [y/N] ").strip().lower()
            if answer not in ("y", "yes", "j", "ja"):
                raise VaultError(f"Not allowed, so {tool.name} didn't run.")
            vault.allow(tool.id, exc.names)
    raise VaultError("The vault stayed locked.")


def _check(home: Home) -> int:
    tools, problems = home.tools()
    engine = find_engine()
    print(f"Engine (uv): {engine or 'not found. Tools with dependencies will not run.'}")
    for t in tools:
        print(f"  ok  {t.name}")
    for p in problems:
        print(f"  !   {p.path.name}: {p.message}")
    return 0 if not problems else 1


def _history(home: Home, query: str | None) -> int:
    tool_id = home.find(query).id if query else None
    records = history(home, tool_id)
    if not records:
        print("No runs yet.")
        return 0
    for r in records:
        took = _duration(r["seconds"]) if "seconds" in r else ""
        print(f"  {r['started'].replace('T', ' ')}  {r['tool_name']:<24} {r['status']:<8} {took}")
    return 0


def _show_value(value: Any) -> str:
    if isinstance(value, bool):
        return "on" if value else "off"
    return "(empty)" if value is None else str(value)


def _duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f} s"
    m, s = divmod(int(round(seconds)), 60)
    return f"{m} min {s} s"


class _Bar:
    def __init__(self, enabled: bool):
        self.enabled = enabled
        self.shown = False
        self.last = 0.0

    def draw(self, fraction: float | None, step: str) -> None:
        if not self.enabled:
            if step:
                print(f"  … {step}")
            return
        now = time.monotonic()
        if now - self.last < 0.05:
            return
        self.last = now
        width = 28
        filled = int((fraction or 0) * width)
        pct = f"{int((fraction or 0) * 100):3d}%" if fraction is not None else "    "
        sys.stdout.write(f"\r  [{'#' * filled}{'.' * (width - filled)}] {pct}  {step[:40]:<40}")
        sys.stdout.flush()
        self.shown = True

    def clear(self) -> None:
        if self.enabled and self.shown:
            sys.stdout.write("\r" + " " * 82 + "\r")
            sys.stdout.flush()
            self.shown = False


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
