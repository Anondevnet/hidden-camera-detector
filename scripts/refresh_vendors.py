#!/usr/bin/env python3
"""Refresh src/hcd/data/camera_vendors.json from the public IEEE MA-L listing.

The organization-to-brand mapping is taken from the existing JSON (the
`organizations` list on each vendor). New prefixes assigned to those same
IEEE registrant names are added. Registrants that are not already in the
file are left out on purpose: this is a curated camera / IoT subset, not
a full OUI database.

Usage:
    python scripts/refresh_vendors.py [--csv path-or-url]
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import urllib.request
from datetime import date
from pathlib import Path

IEEE_CSV = "https://standards-oui.ieee.org/oui/oui.csv"
ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "src" / "hcd" / "data" / "camera_vendors.json"
ANDROID_COPY = ROOT / "android" / "app" / "src" / "main" / "assets" / "camera_vendors.json"


def load_csv(source: str) -> list[dict[str, str]]:
    if source.startswith("https://") or source.startswith("http://"):
        with urllib.request.urlopen(source, timeout=60) as response:  # noqa: S310
            raw = response.read().decode("utf-8", errors="replace")
        handle: io.StringIO | Path | io.TextIOWrapper = io.StringIO(raw)
        close = False
    else:
        handle = open(source, encoding="utf-8", errors="replace")  # noqa: SIM115
        close = True
    try:
        return list(csv.DictReader(handle))
    finally:
        if close:
            handle.close()  # type: ignore[union-attr]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default=IEEE_CSV, help="IEEE MA-L CSV path or URL")
    args = parser.parse_args()

    current = json.loads(OUTPUT.read_text(encoding="utf-8"))
    org_to_vendor: dict[str, dict] = {}
    for vendor in current["vendors"]:
        vendor["prefixes"] = []
        for org in vendor["organizations"]:
            org_to_vendor[org] = vendor

    rows = load_csv(args.csv)
    unknown = 0
    for row in rows:
        if (row.get("Registry") or "").strip() != "MA-L":
            continue
        org = (row.get("Organization Name") or "").strip()
        prefix = (row.get("Assignment") or "").strip().upper()
        vendor = org_to_vendor.get(org)
        if vendor is None:
            unknown += 1
            continue
        if prefix and prefix not in vendor["prefixes"]:
            vendor["prefixes"].append(prefix)

    for vendor in current["vendors"]:
        vendor["prefixes"] = sorted(set(vendor["prefixes"]))

    current["version"] = date.today().isoformat()
    current["source"]["retrieved"] = date.today().isoformat()
    current["source"]["url"] = IEEE_CSV if args.csv.startswith("http") else current["source"].get("url", IEEE_CSV)
    text = json.dumps(current, indent=2) + "\n"
    OUTPUT.write_text(text, encoding="utf-8")
    if ANDROID_COPY.parent.is_dir():
        ANDROID_COPY.write_text(text, encoding="utf-8")
    total = sum(len(v["prefixes"]) for v in current["vendors"])
    print(f"Wrote {OUTPUT} ({len(current['vendors'])} vendors, {total} prefixes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
