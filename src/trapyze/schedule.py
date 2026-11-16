"""Plans: run a tool or chain at set times, also with nobody at the computer.

traPYze keeps the plans in .trapyze/schedules.json. The computer's own
scheduler does the waking up, so plans run while traPYze is closed:

- Windows: Task Scheduler, one task per plan under "\\traPYze\\". It can wake
  the computer from sleep (and on most PCs from hibernation) and can run while
  you're logged out (Windows then needs your password once; it keeps it, not
  traPYze).
- Linux: your crontab. No waking; runs while logged out if the computer is on.
- macOS: a launchd agent. No waking; runs while you're logged in.

Each of those starts `trapyze fire <plan>`. That checks the plan really is
due (or was missed and should catch up), makes sure it runs only once per
time (the open traPYze window checks too), and runs it, or hands it to the
open traPYze so you can watch it there.
"""

from __future__ import annotations

import calendar
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

from .store import StoreError, _clean_name, _read, _write

DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_TIME = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
ON_TIME = dt.timedelta(minutes=10)  # this late still counts as on time
TASK_FOLDER = "\\traPYze\\"
CRON_BEGIN, CRON_END = "# >>> traPYze plans (managed by traPYze; edit them in its Schedule screen)", "# <<< traPYze plans"

_lock = threading.RLock()


# The "when" ------------------------------------------------------------------
def _hm(text: str, what: str = "time") -> tuple[int, int]:
    m = _TIME.match(str(text or "").strip())
    if not m:
        raise StoreError(f"Write the {what} as hours:minutes on a 24-hour clock, for example 07:30.")
    return int(m.group(1)), int(m.group(2))


def check_when(when: dict[str, Any]) -> dict[str, Any]:
    """Validate and tidy a "when" from the Schedule screen."""
    kind = when.get("kind")
    if kind == "weekly":
        days = sorted({int(d) for d in when.get("days") or [] if str(d).isdigit() and 0 <= int(d) <= 6})
        if not days:
            raise StoreError("Choose at least one day.")
        times = sorted({"%02d:%02d" % _hm(t) for t in when.get("times") or []})
        if not times:
            raise StoreError("Add at least one time.")
        if len(times) > 24:
            raise StoreError("At most 24 times a day. For more, use 'Repeatedly'.")
        return {"kind": kind, "days": days, "times": times}
    if kind == "interval":
        days = sorted({int(d) for d in when.get("days") or [] if str(d).isdigit() and 0 <= int(d) <= 6})
        if not days:
            raise StoreError("Choose at least one day.")
        unit = when.get("unit") if when.get("unit") in ("minutes", "hours") else "hours"
        try:
            every = int(when.get("every"))
        except (TypeError, ValueError):
            raise StoreError("Say how often, as a whole number.") from None
        minutes = every * (60 if unit == "hours" else 1)
        if every < 1 or minutes < 5 or minutes > 12 * 60:
            raise StoreError("Choose from every 5 minutes up to every 12 hours.")
        start, end = _hm(when.get("from"), "start time"), _hm(when.get("to"), "end time")
        if end <= start:
            raise StoreError("The end time must be later than the start time.")
        return {"kind": kind, "every": every, "unit": unit, "from": "%02d:%02d" % start, "to": "%02d:%02d" % end, "days": days}
    if kind == "monthly":
        day = when.get("day")
        if day != "last":
            try:
                day = int(day)
            except (TypeError, ValueError):
                raise StoreError("Choose a day of the month.") from None
            if not 1 <= day <= 28:
                raise StoreError("Choose a day from 1 to 28, or the last day (not every month has a 29th to 31st).")
        return {"kind": kind, "day": day, "time": "%02d:%02d" % _hm(when.get("time"))}
    if kind == "once":
        try:
            at = dt.datetime.fromisoformat(str(when.get("at") or "")).replace(second=0, microsecond=0, tzinfo=None)
        except ValueError:
            raise StoreError("Choose a date and a time.") from None
        return {"kind": kind, "at": at.isoformat(timespec="minutes")}
    raise StoreError("Choose when: on days, repeatedly, monthly or once.")


def times_of_day(when: dict[str, Any]) -> list[tuple[int, int]]:
    if when["kind"] == "weekly":
        return [_hm(t) for t in when["times"]]
    if when["kind"] == "interval":
        step = when["every"] * (60 if when["unit"] == "hours" else 1)
        (h1, m1), (h2, m2) = _hm(when["from"]), _hm(when["to"])
        return [divmod(t, 60) for t in range(h1 * 60 + m1, h2 * 60 + m2 + 1, step)]
    if when["kind"] == "monthly":
        return [_hm(when["time"])]
    at = dt.datetime.fromisoformat(when["at"])
    return [(at.hour, at.minute)]


def _on_day(when: dict[str, Any], day: dt.date) -> list[dt.datetime]:
    kind = when["kind"]
    if kind in ("weekly", "interval") and day.weekday() not in when["days"]:
        return []
    if kind == "monthly":
        want = calendar.monthrange(day.year, day.month)[1] if when["day"] == "last" else when["day"]
        if day.day != want:
            return []
    if kind == "once":
        at = dt.datetime.fromisoformat(when["at"])
        return [at] if at.date() == day else []
    return [dt.datetime.combine(day, dt.time(h, m)) for h, m in times_of_day(when)]


def occurrences(when: dict[str, Any], start: dt.datetime, end: dt.datetime) -> Iterator[dt.datetime]:
    """Every planned time with start < t <= end, in order (local clock time)."""
    day = start.date()
    while day <= end.date():
        for t in _on_day(when, day):
            if start < t <= end:
                yield t
        day += dt.timedelta(days=1)


def next_times(when: dict[str, Any], now: dt.datetime, count: int = 1) -> list[dt.datetime]:
    if when["kind"] == "once":
        at = dt.datetime.fromisoformat(when["at"])
        return [at] if at > now else []
    found: list[dt.datetime] = []
    for t in occurrences(when, now, now + dt.timedelta(days=400)):
        found.append(t)
        if len(found) >= count:
            break
    return found


def last_time(when: dict[str, Any], now: dt.datetime) -> dt.datetime | None:
    if when["kind"] == "once":
        at = dt.datetime.fromisoformat(when["at"])
        return at if at <= now else None
    found = None
    for t in occurrences(when, now - dt.timedelta(days=32), now):
        found = t
    return found


def _days_words(days: list[int]) -> str:
    if days == list(range(7)):
        return "every day"
    if days == list(range(5)):
        return "every weekday"
    if days == [5, 6]:
        return "every Saturday and Sunday"
    names = [DAYS[d] for d in days]
    return "every " + (names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1])


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def describe(when: dict[str, Any]) -> str:
    kind = when["kind"]
    if kind == "weekly":
        days = _days_words(when["days"])
        return f"{days[0].upper()}{days[1:]} at {_join(when['times'])}"
    if kind == "interval":
        every = when["every"]
        unit = when["unit"][:-1] if every == 1 else when["unit"]
        how = f"Every {unit}" if every == 1 else f"Every {every} {unit}"
        return f"{how} from {when['from']} to {when['to']}, {_days_words(when['days'])}"
    if kind == "monthly":
        day = "the last day" if when["day"] == "last" else f"the {_ordinal(when['day'])}"
        return f"On {day} of every month at {when['time']}"
    return "Once, on " + nice_time(dt.datetime.fromisoformat(when["at"]), with_year=True)


def nice_time(t: dt.datetime, now: dt.datetime | None = None, with_year: bool = False) -> str:
    now = now or dt.datetime.now()
    clock = t.strftime("%H:%M")
    if t.date() == now.date():
        return f"today at {clock}"
    if t.date() == now.date() + dt.timedelta(days=1):
        return f"tomorrow at {clock}"
    if t.date() == now.date() - dt.timedelta(days=1):
        return f"yesterday at {clock}"
    date = f"{DAYS[t.weekday()]} {t.day} {calendar.month_name[t.month]}"
    if with_year or t.year != now.year:
        date += f" {t.year}"
    return f"{date} at {clock}"


# Plans ---------------------------------------------------------------------
class Plans:
    def __init__(self, internal: Path):
        self.internal = internal
        self.path = internal / "schedules.json"
        self.fired_path = internal / "schedule_fired.json"
        self.log_path = internal / "schedule_log.jsonl"

    def all(self) -> list[dict[str, Any]]:
        return list(_read(self.path, {"plans": []}).get("plans", []))

    def get(self, ref: str) -> dict[str, Any]:
        q = (ref or "").strip().lower()
        for p in self.all():
            if p["id"] == ref or p["name"].lower() == q:
                return p
        raise StoreError(f"There's no plan called '{ref}'.")

    def _save_all(self, plans: list[dict[str, Any]]) -> None:
        _write(self.path, {"plans": plans})

    def save(self, body: dict[str, Any], tools: list, chains: list, presets) -> dict[str, Any]:
        kind, target_id = body.get("target_kind"), str(body.get("target") or "")
        if kind == "tool":
            target = next((t for t in tools if t.id == target_id), None)
        elif kind == "chain":
            target = next((c for c in chains if c.id == target_id), None)
        else:
            target = None
        if target is None:
            raise StoreError("Choose what to run.")
        use = str(body.get("use") or "last")
        if kind == "tool":
            if use.startswith("preset:") and use[7:] not in presets.for_tool(target_id):
                raise StoreError(f"{target.name} has no preset “{use[7:]}”.")
            if use not in ("last", "standard") and not use.startswith("preset:"):
                raise StoreError("Choose which settings to use.")
        when = check_when(dict(body.get("when") or {}))
        if when["kind"] == "once" and dt.datetime.fromisoformat(when["at"]) <= dt.datetime.now():
            raise StoreError("That time has already passed. Choose a time in the future.")
        name = _clean_name(body.get("name") or target.name, "plan")
        plan = {
            "id": str(body.get("id") or "") or uuid.uuid4().hex[:10],
            "name": name, "target_kind": kind, "target": target_id, "use": use if kind == "tool" else "chain",
            "when": when, "enabled": bool(body.get("enabled", True)), "wake": bool(body.get("wake", True)),
            "logged_out": bool(body.get("logged_out", False)),
            "missed": "skip" if body.get("missed") == "skip" else "run",
        }
        with _lock:
            plans = self.all()
            old = next((p for p in plans if p["id"] == plan["id"]), None)
            if body.get("id") and old is None:
                raise StoreError("That plan doesn't exist any more.")
            if any(p["name"].lower() == name.lower() and p["id"] != plan["id"] for p in plans):
                raise StoreError(f"There's already a plan called '{name}'.")
            if old:
                plan["created"] = old.get("created")
                plan["sync"] = old.get("sync")
                plans = [plan if p["id"] == plan["id"] else p for p in plans]
            else:
                plan["created"] = time.time()
                plans.append(plan)
                if when["kind"] != "once":  # times before the plan existed don't count as missed
                    self._set_fired(plan["id"], dt.datetime.now())
            self._save_all(plans)
        return plan

    def update(self, plan_id: str, **changes: Any) -> dict[str, Any]:
        with _lock:
            plans = self.all()
            for p in plans:
                if p["id"] == plan_id:
                    p.update(changes)
                    self._save_all(plans)
                    return p
        raise StoreError("That plan doesn't exist any more.")

    def delete(self, plan_id: str) -> dict[str, Any]:
        with _lock:
            plans = self.all()
            gone = next((p for p in plans if p["id"] == plan_id), None)
            if gone is None:
                raise StoreError("That plan doesn't exist any more.")
            self._save_all([p for p in plans if p["id"] != plan_id])
            return gone

    # What has happened ----------------------------------------------------
    def fired(self) -> dict[str, str]:
        return _read(self.fired_path, {})

    def _set_fired(self, plan_id: str, t: dt.datetime) -> None:
        data = self.fired()
        data[plan_id] = t.isoformat(timespec="minutes")
        _write(self.fired_path, data)

    def log(self, entry: dict[str, Any]) -> None:
        self.internal.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        try:  # keep the log small: the last 500 lines
            lines = self.log_path.read_text(encoding="utf-8").splitlines()
            if len(lines) > 600:
                self.log_path.write_text("\n".join(lines[-500:]) + "\n", encoding="utf-8")
        except OSError:
            pass

    def history(self, plan_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        try:
            lines = self.log_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        out = []
        for line in reversed(lines):
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if plan_id is None or e.get("plan") == plan_id:
                out.append(e)
                if len(out) >= limit:
                    break
        return out

    def update_log(self, plan_id: str, occurrence: str, **changes: Any) -> None:
        """Fill in how a run ended (it was logged as 'running' when it started)."""
        with _lock:
            try:
                lines = self.log_path.read_text(encoding="utf-8").splitlines()
            except OSError:
                return
            for i in range(len(lines) - 1, -1, -1):
                try:
                    e = json.loads(lines[i])
                except ValueError:
                    continue
                if e.get("plan") == plan_id and e.get("occurrence") == occurrence:
                    e.update(changes)
                    lines[i] = json.dumps(e, ensure_ascii=False)
                    self.log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                    return

    # The decision ---------------------------------------------------------
    def due(self, plan: dict[str, Any], now: dt.datetime) -> tuple[str, dt.datetime | None]:
        """("run" | "missed" | "nothing", the planned time it's about)."""
        if not plan.get("enabled", True):
            return "nothing", None
        when = plan["when"]
        last = last_time(when, now)
        if last is None:
            return "nothing", None
        done = self.fired().get(plan["id"])
        if done and dt.datetime.fromisoformat(done) >= last:
            return "nothing", last
        if now - last <= ON_TIME:
            return "run", last
        upcoming = next_times(when, now)
        if plan.get("missed", "run") == "run" and (not upcoming or upcoming[0] > now) and now - last <= dt.timedelta(days=3):
            return "run", last  # catch up: the computer was off or asleep at that time
        return "missed", last

    def claim(self, plan: dict[str, Any], now: dt.datetime) -> tuple[str, dt.datetime | None]:
        """Decide and mark as handled in one step, so only one caller runs it."""
        with exclusive(self.internal / "schedule.lock"):
            verdict, at = self.due(plan, now)
            if verdict in ("run", "missed") and at is not None:
                self._set_fired(plan["id"], at)
                if verdict == "missed":
                    self.log({"plan": plan["id"], "name": plan["name"], "occurrence": at.isoformat(timespec="minutes"),
                              "status": "missed", "at": time.time(),
                              "note": "The computer was off or asleep at that time, and this plan skips missed runs."})
            return verdict, at


@contextmanager
def exclusive(path: Path) -> Iterator[None]:
    """A lock between processes (the window and a background run deciding at once)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock, open(path, "a+b") as f:
        if sys.platform.startswith("win"):
            import msvcrt

            f.seek(0)
            for _ in range(600):
                try:
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.05)
            try:
                yield
            finally:
                f.seek(0)
                try:
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
        else:
            import fcntl

            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)


# Background tasks per operating system -----------------------------------------
def launcher(home_root: Path, plan_id: str) -> tuple[str, list[str]]:
    exe = Path(sys.executable)
    quiet = exe.with_name("pythonw.exe")
    program = quiet if sys.platform.startswith("win") and quiet.exists() else exe
    return str(program), ["-m", "trapyze", "--home", str(home_root), "fire", plan_id]


def _task_name(plan: dict[str, Any]) -> str:
    safe = re.sub(r"[^\w .()-]", "", plan["name"]).strip()[:60] or "plan"
    return f"{safe} ({plan['id']})"


def windows_xml(plan: dict[str, Any], home_root: Path, user: str, today: dt.date | None = None) -> str:
    """A Task Scheduler task for a plan, as the XML Windows imports."""
    ns = "http://schemas.microsoft.com/windows/2004/02/mit/task"
    ET.register_namespace("", ns)
    q = lambda tag: f"{{{ns}}}{tag}"  # noqa: E731
    task = ET.Element(q("Task"), {"version": "1.2"})

    def sub(parent, tag, text=None):
        el = ET.SubElement(parent, q(tag))
        if text is not None:
            el.text = str(text)
        return el

    reg = sub(task, "RegistrationInfo")
    sub(reg, "Author", "traPYze")
    sub(reg, "Description", f"traPYze plan “{plan['name']}”: {describe(plan['when'])}. Change it in traPYze, not here.")
    triggers = sub(task, "Triggers")
    when, today = plan["when"], today or dt.date.today()

    def calendar_trigger(h, m, repetition=None):
        t = sub(triggers, "CalendarTrigger")
        if repetition:
            rep = sub(t, "Repetition")
            sub(rep, "Interval", repetition[0])
            sub(rep, "Duration", repetition[1])
            sub(rep, "StopAtDurationEnd", "false")
        sub(t, "StartBoundary", f"{today.isoformat()}T{h:02d}:{m:02d}:00")
        sub(t, "Enabled", "true")
        return t

    def by_days(t, days):
        if days == list(range(7)):
            d = sub(t, "ScheduleByDay")
            sub(d, "DaysInterval", 1)
        else:
            w = sub(t, "ScheduleByWeek")
            dow = sub(w, "DaysOfWeek")
            for d in days:
                sub(dow, DAYS[d])
            sub(w, "WeeksInterval", 1)

    if when["kind"] == "weekly":
        for h, m in times_of_day(when):
            by_days(calendar_trigger(h, m), when["days"])
    elif when["kind"] == "interval":
        step = when["every"] * (60 if when["unit"] == "hours" else 1)
        (h1, m1), (h2, m2) = _hm(when["from"]), _hm(when["to"])
        span = h2 * 60 + m2 - (h1 * 60 + m1) + 1
        by_days(calendar_trigger(h1, m1, (f"PT{step}M", f"PT{span}M")), when["days"])
    elif when["kind"] == "monthly":
        h, m = _hm(when["time"])
        t = calendar_trigger(h, m)
        bm = sub(t, "ScheduleByMonth")
        dom = sub(bm, "DaysOfMonth")
        sub(dom, "Day", "Last" if when["day"] == "last" else when["day"])
        months = sub(bm, "Months")
        for name in calendar.month_name[1:]:
            sub(months, name)
    else:
        t = sub(triggers, "TimeTrigger")
        sub(t, "StartBoundary", dt.datetime.fromisoformat(when["at"]).isoformat(timespec="seconds"))
        sub(t, "Enabled", "true")
    principal = sub(sub(task, "Principals"), "Principal", None)
    principal.set("id", "Author")
    sub(principal, "UserId", user)
    sub(principal, "LogonType", "Password" if plan.get("logged_out") else "InteractiveToken")
    sub(principal, "RunLevel", "LeastPrivilege")
    s = sub(task, "Settings")
    for tag, value in (("MultipleInstancesPolicy", "IgnoreNew"), ("DisallowStartIfOnBatteries", "false"),
                       ("StopIfGoingOnBatteries", "false"), ("AllowHardTerminate", "true"),
                       ("StartWhenAvailable", "true" if plan.get("missed", "run") == "run" else "false"),
                       ("RunOnlyIfNetworkAvailable", "false")):
        sub(s, tag, value)
    idle = sub(s, "IdleSettings")
    sub(idle, "StopOnIdleEnd", "false")
    sub(idle, "RestartOnIdle", "false")
    for tag, value in (("AllowStartOnDemand", "true"), ("Enabled", "true" if plan.get("enabled", True) else "false"),
                       ("Hidden", "false"), ("RunOnlyIfIdle", "false"), ("WakeToRun", "true" if plan.get("wake") else "false"),
                       ("ExecutionTimeLimit", "PT12H"), ("Priority", "7")):
        sub(s, tag, value)
    actions = sub(task, "Actions")
    actions.set("Context", "Author")
    ex = sub(actions, "Exec")
    program, args = launcher(home_root, plan["id"])
    sub(ex, "Command", program)
    sub(ex, "Arguments", " ".join(f'"{a}"' if " " in a else a for a in args))
    sub(ex, "WorkingDirectory", str(home_root))
    return '<?xml version="1.0" encoding="UTF-16"?>\n' + ET.tostring(task, encoding="unicode")


def cron_lines(plans: list[dict[str, Any]], home_root: Path) -> list[str]:
    """crontab lines. They may start a little too often (cron can't say 'last day of the
    month'); `trapyze fire` checks the plan really is due."""
    lines = []
    for plan in plans:
        if not plan.get("enabled", True):
            continue
        when = plan["when"]
        program, args = launcher(home_root, plan["id"])
        command = " ".join(_sh(a) for a in [program, *args]) + " >/dev/null 2>&1"
        if when["kind"] in ("weekly", "interval"):
            dow = ",".join(str((d + 1) % 7) for d in when["days"])  # cron: 0 = Sunday
            dom, month = "*", "*"
        elif when["kind"] == "monthly":
            dow, month = "*", "*"
            dom = "28-31" if when["day"] == "last" else str(when["day"])
        else:
            at = dt.datetime.fromisoformat(when["at"])
            dow, dom, month = "*", str(at.day), str(at.month)
        by_minute: dict[int, list[int]] = {}
        for h, m in times_of_day(when):
            by_minute.setdefault(m, []).append(h)
        for m, hours in sorted(by_minute.items()):
            lines.append(f"{m} {','.join(str(h) for h in sorted(set(hours)))} {dom} {month} {dow} {command}  # trapyze:{plan['id']}")
    return lines


def _sh(text: str) -> str:
    return text if re.match(r"^[\w./:=-]+$", text) else "'" + text.replace("'", "'\\''") + "'"


def launchd_plist(plan: dict[str, Any], home_root: Path) -> str:
    import plistlib

    when = plan["when"]
    entries: list[dict[str, int]] = []
    for h, m in times_of_day(when):
        if when["kind"] in ("weekly", "interval"):
            entries += [{"Weekday": (d + 1) % 7, "Hour": h, "Minute": m} for d in when["days"]]
        elif when["kind"] == "monthly":
            days = range(28, 32) if when["day"] == "last" else [when["day"]]
            entries += [{"Day": d, "Hour": h, "Minute": m} for d in days]
        else:
            at = dt.datetime.fromisoformat(when["at"])
            entries.append({"Month": at.month, "Day": at.day, "Hour": h, "Minute": m})
    program, args = launcher(home_root, plan["id"])
    data = {"Label": f"org.trapyze.plan.{plan['id']}", "ProgramArguments": [program, *args],
            "StartCalendarInterval": entries, "WorkingDirectory": str(home_root), "ProcessType": "Background"}
    return plistlib.dumps(data).decode("utf-8")


def plan_hash(plan: dict[str, Any]) -> str:
    keep = {k: plan.get(k) for k in ("name", "when", "enabled", "wake", "logged_out", "missed")}
    return hashlib.sha256(json.dumps(keep, sort_keys=True).encode()).hexdigest()[:16]


class System:
    """Talks to the computer's own scheduler. `run` is swappable for tests."""

    def __init__(self, home_root: Path, platform: str | None = None,
                 run: Callable[..., subprocess.CompletedProcess] | None = None):
        self.root = home_root
        self.platform = platform or sys.platform
        self._run = run or (lambda cmd, **kw: subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                                                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), **kw))

    @property
    def name(self) -> str:
        if self.platform.startswith("win"):
            return "Windows Task Scheduler"
        if self.platform == "darwin":
            return "macOS launchd"
        return "cron"

    def abilities(self) -> dict[str, bool]:
        win = self.platform.startswith("win")
        return {"wake": win, "logged_out": win or not self.platform == "darwin", "password": win}

    def install(self, plan: dict[str, Any], all_plans: list[dict[str, Any]], password: str | None = None) -> None:
        if self.platform.startswith("win"):
            self._win_install(plan, password)
        elif self.platform == "darwin":
            self._mac_install(plan)
        else:
            self._cron_write(all_plans)

    def remove(self, plan: dict[str, Any], all_plans: list[dict[str, Any]]) -> None:
        if self.platform.startswith("win"):
            script = ("Unregister-ScheduledTask -TaskPath $env:TZ_PATH -TaskName $env:TZ_NAME -Confirm:$false "
                      "-ErrorAction SilentlyContinue")
            self._ps(script, {"TZ_PATH": TASK_FOLDER, "TZ_NAME": plan.get("task_name") or _task_name(plan)})
        elif self.platform == "darwin":
            path = Path.home() / "Library" / "LaunchAgents" / f"org.trapyze.plan.{plan['id']}.plist"
            self._run(["launchctl", "bootout", f"gui/{os.getuid()}", str(path)])
            path.unlink(missing_ok=True)
        else:
            self._cron_write([p for p in all_plans if p["id"] != plan["id"]])

    # Windows
    def _ps(self, script: str, env: dict[str, str], stdin: str | None = None) -> str:
        done = self._run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                         env={**os.environ, **env}, input=stdin)
        if done.returncode != 0:
            raise OSError(_plain_windows_error(done.stderr or done.stdout))
        return done.stdout

    def _win_install(self, plan: dict[str, Any], password: str | None) -> None:
        user = f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}".strip("\\")
        xml = windows_xml(plan, self.root, user)
        if plan.get("logged_out") and not password:
            raise NeedsPassword("To run while you're logged out, Windows needs your password once.")
        old = plan.get("task_name")
        if old and old != _task_name(plan):
            self.remove({**plan, "task_name": old}, [])
        script = (
            "$xml = [IO.File]::ReadAllText($env:TZ_XML);"
            "if ($env:TZ_PASSWORD_GIVEN -eq '1') { $pw = [Console]::In.ReadLine();"
            " Register-ScheduledTask -TaskPath $env:TZ_PATH -TaskName $env:TZ_NAME -Xml $xml -User $env:TZ_USER -Password $pw -Force | Out-Null }"
            " else { Register-ScheduledTask -TaskPath $env:TZ_PATH -TaskName $env:TZ_NAME -Xml $xml -Force | Out-Null }"
        )
        folder = Path(os.environ.get("TEMP") or self.root)
        tmp = folder / f"trapyze-task-{plan['id']}.xml"
        tmp.write_text(xml, encoding="utf-16")
        try:
            self._ps(script, {"TZ_XML": str(tmp), "TZ_PATH": TASK_FOLDER, "TZ_NAME": _task_name(plan), "TZ_USER": user,
                              "TZ_PASSWORD_GIVEN": "1" if password else "0"},
                     stdin=(password + "\n") if password else None)  # never on the command line
        finally:
            tmp.unlink(missing_ok=True)

    # macOS
    def _mac_install(self, plan: dict[str, Any]) -> None:
        folder = Path.home() / "Library" / "LaunchAgents"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"org.trapyze.plan.{plan['id']}.plist"
        self._run(["launchctl", "bootout", f"gui/{os.getuid()}", str(path)])
        if not plan.get("enabled", True):
            path.unlink(missing_ok=True)
            return
        path.write_text(launchd_plist(plan, self.root), encoding="utf-8")
        done = self._run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(path)])
        if done.returncode != 0:
            raise OSError((done.stderr or "launchd didn't accept the plan.").strip())

    # Linux
    def _cron_write(self, plans: list[dict[str, Any]]) -> None:
        current = self._run(["crontab", "-l"])
        if current.returncode != 0 and "no crontab" not in (current.stderr or "").lower():
            raise OSError("cron isn't available here (the crontab command failed). Plans run only while traPYze is open.")
        text = current.stdout if current.returncode == 0 else ""
        kept, skipping = [], False
        for line in text.splitlines():
            if line.strip() == CRON_BEGIN:
                skipping = True
            elif line.strip() == CRON_END:
                skipping = False
            elif not skipping:
                kept.append(line)
        while kept and not kept[-1].strip():
            kept.pop()
        ours = cron_lines(plans, self.root)
        new = "\n".join(kept + ([""] if kept else []) + ([CRON_BEGIN, *ours, CRON_END] if ours else [])) + "\n"
        done = self._run(["crontab", "-"], input=new)
        if done.returncode != 0:
            raise OSError((done.stderr or "cron didn't accept the plans.").strip())


class NeedsPassword(StoreError):
    """Windows wants the password to run a plan while logged out."""


def _plain_windows_error(text: str) -> str:
    low = (text or "").lower()
    if "user name or password is incorrect" in low or "logon failure" in low or "0x8007052e" in low:
        return "Windows says the password is wrong. Use the password you log in to Windows with."
    if "access is denied" in low or "0x80070005" in low:
        return "Windows refused (access denied). Try again with 'Only while I'm logged in', or ask for administrator rights."
    first = next((line.strip() for line in (text or "").splitlines() if line.strip()), "")
    return f"Windows Task Scheduler said: {first or 'something went wrong.'}"


def sync(plans: Plans, system: System, plan: dict[str, Any] | None = None, password: str | None = None,
         removed: dict[str, Any] | None = None) -> None:
    """Bring the computer's scheduler in line with a changed (or removed) plan."""
    if removed is not None:
        system.remove(removed, plans.all())
        return
    assert plan is not None
    try:
        system.install(plan, plans.all(), password)
        plans.update(plan["id"], sync={"ok": True, "at": time.time(), "hash": plan_hash(plan), "by": system.name,
                                       "message": ""}, task_name=_task_name(plan))
    except NeedsPassword:
        raise
    except (OSError, subprocess.SubprocessError) as exc:
        plans.update(plan["id"], sync={"ok": False, "at": time.time(), "hash": plan_hash(plan), "by": system.name,
                                       "message": str(exc)})


# Running a plan ----------------------------------------------------------------
def remembered(home) -> dict[str, dict[str, Any]]:
    try:
        return json.loads((home.internal / "last_settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def plan_settings(home, plan: dict[str, Any]) -> dict[str, Any]:
    from .store import Presets, Step, step_settings

    return step_settings(Step(plan["target"], plan["use"]), Presets(home.internal), remembered(home))


def run_here(home, plan: dict[str, Any], at: dt.datetime, how: str = "background") -> str:
    """Run a plan in this process (nobody at the computer) and log how it went."""
    from .runner import Run
    from .store import ChainRun, Chains, Presets, step_settings
    from .vault import Vault, VaultError, secrets_for

    plans = Plans(home.internal)
    entry = {"plan": plan["id"], "name": plan["name"], "occurrence": at.isoformat(timespec="minutes"),
             "status": "running", "at": time.time(), "how": how}
    plans.log(entry)
    vault = Vault(home.internal)
    tools = {t.id: t for t in home.tools()[0]}

    def start(tool_id: str, chosen: dict[str, Any]) -> Run:
        from .review import Reviews
        tool = tools[tool_id]
        if Reviews(home.internal).pending(tool.id):
            raise StoreError(f"{tool.name} is new here and waits for a look. Run it once yourself in traPYze first.")
        env, secret = secrets_for(vault, tool.id, tool.name, tool.connections, unattended=True)
        return Run(home, tool, chosen, extra_env=env, secrets=secret).start()

    try:
        if plan["target_kind"] == "tool":
            if plan["target"] not in tools:
                raise StoreError(f"The tool '{plan['target']}' isn't in the scripts folder any more.")
            run = start(plan["target"], plan_settings(home, plan))
            plans.update_log(plan["id"], entry["occurrence"], run_id=run.run_id)
            result = run.wait()
            status, note = result.status, result.cause or ""
        else:
            chain = Chains(home.internal).get(plan["target"])
            missing = [s.tool for s in chain.steps if s.tool not in tools]
            if missing:
                raise StoreError(f"The chain uses tools that aren't there any more: {', '.join(missing)}.")
            settings = [step_settings(s, Presets(home.internal), remembered(home)) for s in chain.steps]
            cr = ChainRun(chain, settings, {t.id: t.name for t in tools.values()}, start).begin()
            status = cr.wait()
            problems = [f"{s['name']}: {s['message']}" for s in cr.steps if s["status"] == "failed" and s["message"]]
            note = "; ".join(problems)
    except (StoreError, VaultError, LookupError, OSError, RuntimeError, ValueError) as exc:
        status, note = "failed", str(exc)
    plans.update_log(plan["id"], entry["occurrence"], status=status, note=note, ended=time.time())
    return status


def fire(home, plan_id: str, now: dt.datetime | None = None, force: bool = False) -> int:
    """What the computer's scheduler starts. Quiet: nobody may be watching."""
    plans = Plans(home.internal)
    try:
        plan = plans.get(plan_id)
    except StoreError:
        return 0  # the plan was deleted; its task goes on the next sync
    now = now or dt.datetime.now()
    from .desktop import find_running

    info = find_running(home)
    if info:  # traPYze is open: let it run the plan, so it shows up live there
        import urllib.request

        req = urllib.request.Request(f"http://127.0.0.1:{int(info['port'])}/api/schedules/fire",
                                     data=json.dumps({"id": plan_id, "force": force}).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "X-Trapyze-Token": info["token"]})
        try:
            with urllib.request.urlopen(req, timeout=30):
                return 0
        except OSError:
            pass  # it went away in the meantime: run it here
    if force:
        verdict, at = "run", now.replace(second=0, microsecond=0)
    else:
        verdict, at = plans.claim(plan, now)
    if verdict != "run" or at is None:
        return 0
    status = run_here(home, plan, at)
    return 0 if status in ("done", "warning") else 1
