"""Reads a bank's CSV export, whatever the bank: finds the date, amount and description columns itself.

Used by the Home finance tools. Not a tool by itself.
"""

import csv
import datetime
import re
from pathlib import Path

DATE_NAMES = ("date", "datum", "boekdatum", "transactiedatum", "transaction date", "booking date", "posting date",
              "buchungstag", "valutadatum", "value date")
AMOUNT_NAMES = ("amount", "bedrag", "bedrag (eur)", "transactiebedrag", "betrag", "montant", "amount (eur)")
TEXT_NAMES = ("description", "omschrijving", "naam / omschrijving", "name", "naam", "naam tegenpartij", "payee",
              "counterparty", "mededelingen", "memo", "details", "omschrijving-1", "verwendungszweck", "merchant")
SIGN_NAMES = ("af bij", "af/bij", "debit/credit", "credit/debit", "dc", "type")
OUT_NAMES, IN_NAMES = ("debit", "af", "withdrawal", "paid out", "money out"), ("credit", "bij", "deposit", "paid in", "money in")
DATE_FORMATS = ("%Y%m%d", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%y", "%d/%m/%y")


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def amount(text: str) -> float | None:
    t = re.sub(r"[^\d,.\-+()]", "", str(text or ""))
    if not re.search(r"\d", t):
        return None
    negative = t.startswith("-") or t.endswith("-") or (t.startswith("(") and t.endswith(")"))
    t = re.sub(r"[-+()]", "", t)
    if "," in t and "." in t:  # the last one is the decimal mark
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif "," in t:
        t = t.replace(",", ".") if re.search(r",\d{1,2}$", t) else t.replace(",", "")
    try:
        value = float(t)
    except ValueError:
        return None
    return -value if negative else value


def _find(header: list[str], names: tuple[str, ...], chosen: str = "") -> int | None:
    low = [h.strip().lower() for h in header]
    if chosen and chosen.strip().lower() in low:
        return low.index(chosen.strip().lower())
    for name in names:  # exact first, then "contains"
        if name in low:
            return low.index(name)
    for name in names:
        for i, h in enumerate(low):
            if name in h:
                return i
    return None


def _date_format(values: list[str]) -> str | None:
    for fmt in DATE_FORMATS:
        try:
            for v in values:
                datetime.datetime.strptime(v, fmt)
            return fmt
        except ValueError:
            continue
    return None


def read(path: Path, date_col: str = "", amount_col: str = "", text_col: str = "") -> list[dict]:
    """[{date, amount (negative = money out), text}], oldest first. Raises SystemExit with a plain message."""
    text = read_text(path)
    lines = [l for l in text.splitlines() if l.strip()]
    if len(lines) < 2:
        raise SystemExit(f"{path.name} has no rows. Download the transactions as CSV from your bank's website.")
    try:
        dialect = csv.Sniffer().sniff("\n".join(lines[:20]), delimiters=";,\t|")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(lines, dialect))
    # The header is the first row that names a date column and an amount (or debit/credit) column.
    start = next((i for i, r in enumerate(rows[:15]) if _find(r, DATE_NAMES, date_col) is not None
                  and (_find(r, AMOUNT_NAMES, amount_col) is not None or _find(r, OUT_NAMES) is not None)), None)
    if start is None:
        raise SystemExit(f"Couldn't find the date and amount columns in {path.name}. Its first line is: "
                         f"{lines[0][:120]} . Fill in the column names under 'More settings'.")
    header, body = rows[start], [r for r in rows[start + 1:] if len(r) >= 2]
    d, a, t = _find(header, DATE_NAMES, date_col), _find(header, AMOUNT_NAMES, amount_col), _find(header, TEXT_NAMES, text_col)
    sign, out_col, in_col = _find(header, SIGN_NAMES), _find(header, OUT_NAMES), _find(header, IN_NAMES)
    # Banks spread the story over several columns (name, description, remarks): use them all.
    low = [h.strip().lower() for h in header]
    texts = [t] if text_col and t is not None else [i for i, h in enumerate(low) if any(n in h for n in TEXT_NAMES) and i not in (d, a)]
    cell = lambda r, i: r[i].strip() if i is not None and i < len(r) else ""  # noqa: E731
    fmt = _date_format([cell(r, d) for r in body if cell(r, d)][:200])
    if fmt is None:
        raise SystemExit(f"Couldn't read the dates in {path.name} (for example '{cell(body[0], d)}').")
    found = []
    for r in body:
        try:
            day = datetime.datetime.strptime(cell(r, d), fmt).date()
        except ValueError:
            continue
        if a is not None:
            value = amount(cell(r, a))
            if value is not None and sign is not None and sign != a:
                word = cell(r, sign).lower()
                if word in ("af", "debit", "d", "db", "dr", "debet"):
                    value = -abs(value)
                elif word in ("bij", "credit", "c", "cr"):
                    value = abs(value)
        else:
            paid, got = amount(cell(r, out_col)), amount(cell(r, in_col))
            value = (abs(got) if got else 0) - (abs(paid) if paid else 0) if (paid or got) else None
        if value is None:
            continue
        words = " ".join(cell(r, i) for i in texts) if texts else " ".join(c for i, c in enumerate(r) if i not in (d, a))
        found.append({"date": day, "amount": value, "text": " ".join(words.split())})
    if not found:
        raise SystemExit(f"No transactions could be read from {path.name}.")
    return sorted(found, key=lambda x: x["date"])
