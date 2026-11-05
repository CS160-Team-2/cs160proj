"""Reading a delivery manifest, as a pure function with no database.

A manifest is a CSV file a manager uploads when a delivery arrives:

    product_name,quantity
    "Organic Apples, 3 lb bag",24
    Organic Broccoli Crown,30

read_manifest() turns the file's bytes and the catalog into the stock to
add per product, plus every problem it found, each tied to its line in
the file. It never guesses: a name must match one product exactly,
ignoring capitals and extra spaces, or the line is a problem. With no
I/O here, the same file and catalog always give the same answer, and
test_manifest.py can check the rules without a database.

The routes in routes/manifests.py look up the catalog, call this, and
apply the result only when there are no problems at all.
"""

import csv
import hashlib
import io
import re
from dataclasses import dataclass

MAX_BYTES = 1_000_000          # about 1 MB
MAX_LINES = 1000               # product lines, not counting the header
MAX_QUANTITY = 100_000         # per product, after repeated lines are added up
REQUIRED_COLUMNS = ("product_name", "quantity")

WHOLE_NUMBER = re.compile(r"\d+")


@dataclass
class Manifest:
    lines: list        # one per product: product_id, name, quantity, line_numbers, is_listed
    problems: list     # {"line": n or None, "message": "..."}, in file order

    @property
    def ok(self):
        return not self.problems


def fingerprint(raw):
    """SHA-256 of the file's bytes: the same contents, the same fingerprint."""
    return hashlib.sha256(raw).hexdigest()


def normalize(name):
    return " ".join(name.split()).casefold()


def _problem(line, message):
    return {"line": line, "message": message}


def _rows(raw):
    """(line number, cells) for every row, or a problem if it is not a CSV text file."""
    try:
        # utf-8-sig drops the byte order mark Excel adds to "CSV UTF-8" files.
        text = raw.decode("utf-8-sig")
        if "\x00" in text:
            raise ValueError
        reader = csv.reader(io.StringIO(text, newline=""))
        return [(reader.line_num, row) for row in reader], None
    except (UnicodeDecodeError, ValueError, csv.Error):
        return None, _problem(None, "This is not a CSV text file. Save it as CSV (UTF-8) and upload it again.")


def read_manifest(raw, catalog):
    """`catalog` is a list of dicts with product_id, name and is_listed."""
    if len(raw) > MAX_BYTES:
        return Manifest([], [_problem(None, "The file is larger than 1 MB.")])

    rows, unreadable = _rows(raw)
    if unreadable:
        return Manifest([], [unreadable])
    if not rows:
        return Manifest([], [_problem(None, "The file is empty.")])

    header_line, header = rows[0]
    columns = [cell.strip().lower() for cell in header]
    if not all(name in columns for name in REQUIRED_COLUMNS):
        return Manifest([], [_problem(header_line, "The first line must name the columns "
                                                   "product_name and quantity.")])
    name_at, quantity_at = (columns.index(name) for name in REQUIRED_COLUMNS)

    body = [(line, row) for line, row in rows[1:] if any(cell.strip() for cell in row)]
    if not body:
        return Manifest([], [_problem(None, "The manifest lists no products.")])
    if len(body) > MAX_LINES:
        return Manifest([], [_problem(None, f"A manifest can list at most {MAX_LINES} lines; "
                                            f"this one has {len(body)}.")])

    by_name = {}
    for product in catalog:
        by_name.setdefault(normalize(product["name"]), []).append(product)

    totals, problems = {}, []        # totals keeps the order products first appear in
    for line, row in body:
        name = row[name_at].strip() if name_at < len(row) else ""
        quantity = row[quantity_at].strip() if quantity_at < len(row) else ""

        product = None
        if not name:
            problems.append(_problem(line, "The product name is missing."))
        else:
            matches = by_name.get(normalize(name), [])
            if not matches:
                problems.append(_problem(line, f'No product named "{name}".'))
            elif len(matches) > 1:
                problems.append(_problem(line, f'"{name}" matches more than one product. '
                                               "Rename one of them in the inventory first."))
            else:
                product = matches[0]

        if not (WHOLE_NUMBER.fullmatch(quantity) and 1 <= int(quantity) <= MAX_QUANTITY):
            problems.append(_problem(line, f"The quantity must be a whole number from 1 to "
                                           f'{MAX_QUANTITY} (it says "{quantity}").'))
        elif product is not None:
            entry = totals.setdefault(product["product_id"], {
                "product_id": product["product_id"],
                "name": product["name"],
                "quantity": 0,
                "line_numbers": [],
                "is_listed": bool(product["is_listed"]),
            })
            entry["quantity"] += int(quantity)
            entry["line_numbers"].append(line)

    for entry in totals.values():
        if entry["quantity"] > MAX_QUANTITY:
            lines = ", ".join(str(n) for n in entry["line_numbers"])
            problems.append(_problem(entry["line_numbers"][-1],
                                     f'"{entry["name"]}" adds up to {entry["quantity"]} on lines '
                                     f"{lines}; the most for one product is {MAX_QUANTITY}."))

    problems.sort(key=lambda problem: problem["line"] or 0)
    return Manifest(list(totals.values()), problems)
