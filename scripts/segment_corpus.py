#!/usr/bin/env python3
"""Cut the corpus into segments before analysing anything.

WHY SEGMENT FIRST
-----------------
Averaging 49,121 tenders together hides the finding. The clearest example already
measured: the single-bidder rate across confirmed Gurugram is 8.3%, which sounds
unremarkable — until it is split by department, where it runs from 0.0% at XEN TS
Gurugram to 36.8% at Sohana PHED. The corpus-wide number is the one number that tells
you nothing.

The same is true of documents. "96% of documents are rubber stamps" is an average over a
corpus where AOC letters carry agreement amounts and Technical Evaluations carry the word
"approved". Analysing them as one pool produces a statement about neither.

So this builds the map first: every tender assigned to a segment, every segment profiled
on size, money, outcome and — the part that decides whether a segment can be analysed at
all — how much document evidence it actually has. Then a segment is chosen and read
properly, rather than sampling everything shallowly.

WHAT A SEGMENT IS
-----------------
department x work component, because those are the two axes that change behaviour:
who ran the procurement, and what was being bought. Year and value band are carried as
attributes so a segment can be sliced further without recomputing.

Output is a profile table, ordered so the segments worth reading first are at the top:
enough tenders to be worth a conclusion, and enough retrieved documents to support one.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = Path(os.environ.get("CIVIC_STUFF", ROOT.parent / "civic-stuff"))
FINAL = ARCHIVE / "data" / "final"
DERIVED = ARCHIVE / "data" / "derived"
INDEX = ROOT / "public" / "data" / "tender-index.json"
TEXT = ROOT / "build" / "doctext"
OUT = ROOT / "build" / "segments"


def rows(path: Path):
    with open(path, newline="", encoding="utf-8", errors="replace") as handle:
        yield from csv.DictReader(handle)


def number(value) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def value_band(amount: float | None) -> str:
    """Bands chosen to match how the works themselves differ, not round numbers.
    Below 5 lakh is petty works; 5-50 lakh is the bulk of municipal repair; 50 lakh-5
    crore is substantial construction; above that is infrastructure."""
    if amount is None:
        return "no value published"
    if amount < 500_000:
        return "under 5 lakh"
    if amount < 5_000_000:
        return "5-50 lakh"
    if amount < 50_000_000:
        return "50 lakh - 5 crore"
    return "over 5 crore"


def main() -> int:
    index = json.loads(INDEX.read_text())
    columns = {field: position for position, field in enumerate(index["schema"])}
    dictionaries = index["dictionaries"]
    dictionary_fields = set(index["dictionaryFields"])

    def read(row, field):
        value = row[columns[field]]
        if field in dictionary_fields:
            table = dictionaries.get(field, [])
            return table[value] if isinstance(value, int) and 0 <= value < len(table) else ""
        return value

    # Documents retrieved per tender, and how many of them we have text for. A segment
    # with no readable documents cannot be analysed from documents, however many tenders
    # it holds — that is the single most useful thing this table says.
    retrieved = Counter()
    stage_mix = defaultdict(Counter)
    have_text = Counter()
    cached = {p.stem for p in TEXT.rglob("*.txt")} if TEXT.exists() else set()
    for record in rows(FINAL / "documents.csv"):
        sha = (record.get("sha256") or "").strip()
        if not sha:
            continue
        tender = record["tender_id"]
        retrieved[tender] += 1
        stage_mix[tender][record.get("stage_or_section") or ""] += 1
        if sha in cached:
            have_text[tender] += 1

    bids = Counter()
    single = set()
    per_tender_bidders = defaultdict(set)
    for record in rows(FINAL / "bid_history.csv"):
        bids[record["tender_id"]] += 1
        name = (record.get("bidder_name") or "").strip()
        if name:
            per_tender_bidders[record["tender_id"]].add(name)
    for tender, names in per_tender_bidders.items():
        if len(names) == 1:
            single.add(tender)

    # Contract modes ship as a bitmask over `contractModeFlags` (bit i = flag i).
    # They answer HOW the work was bought — an AMC, hired manpower, a recalled tender —
    # which is orthogonal to the component axis this table is built on. Carried per
    # segment because a group that is 80% maintenance contracts must be read differently
    # from one that is 80% new construction, even when the component matches.
    mode_flags = index.get("contractModeFlags") or []

    segments: dict[tuple[str, str], dict] = defaultdict(lambda: {
        "tenders": 0, "awarded": 0, "controlling": 0, "cancelled": 0, "retendered": 0,
        "contract_value": 0.0, "with_bids": 0, "single_bidder": 0,
        "documents": 0, "documents_with_text": 0, "tenders_with_text": 0,
        "years": Counter(), "bands": Counter(), "scopes": Counter(),
        "modes": Counter(),
    })

    # Two cuts from one pass. `department` is the arm of government (48 canonical
    # lines) and hides that MC Gurgaon, MC Sohna and twelve other bodies answer as
    # one line; `departmentUnit` is the leaf office that ran the procurement (189
    # bodies). The parent cut gives totals; the unit cut is where per-office
    # behaviour becomes visible.
    units: dict[tuple[str, str], dict] = defaultdict(segments.default_factory)

    for row in index["rows"]:
        tender = read(row, "id")
        department = read(row, "department") or "Unknown"
        component = read(row, "component") or "unclassified"
        unit = (read(row, "departmentUnit") or "Unknown"
                ) if "departmentUnit" in columns else "Unknown"
        contract = number(row[columns["contractValue"]])
        status = read(row, "status")
        packed = row[columns["contractModes"]] if "contractModes" in columns else 0
        for bucket in (segments[(department, component)], units[(unit, component)]):
            bucket["tenders"] += 1
            bucket["years"][read(row, "year") or "?"] += 1
            bucket["scopes"][read(row, "scope") or "?"] += 1
            if row[columns["isAwarded"]]:
                bucket["awarded"] += 1
            if row[columns["isControllingAward"]]:
                bucket["controlling"] += 1
                if contract is not None:
                    bucket["contract_value"] += contract
            bucket["bands"][value_band(contract)] += 1
            if status == "Cancelled":
                bucket["cancelled"] += 1
            if status == "Retender":
                bucket["retendered"] += 1
            if bids.get(tender):
                bucket["with_bids"] += 1
                if tender in single:
                    bucket["single_bidder"] += 1
            bucket["documents"] += retrieved.get(tender, 0)
            bucket["documents_with_text"] += have_text.get(tender, 0)
            if have_text.get(tender):
                bucket["tenders_with_text"] += 1
            if isinstance(packed, int):
                for bit, flag in enumerate(mode_flags):
                    if packed & (1 << bit):
                        bucket["modes"][flag] += 1

    def build_profile(table: dict[tuple[str, str], dict], key_name: str) -> list[dict]:
        rows_out = []
        for (group, component), bucket in table.items():
            tenders = bucket["tenders"]
            with_bids = bucket["with_bids"]
            rows_out.append({
                key_name: group,
                "component": component,
                "tenders": tenders,
                "awarded": bucket["awarded"],
                "controlling_awards": bucket["controlling"],
                "contract_value_inr": round(bucket["contract_value"], 2),
                "cancelled": bucket["cancelled"],
                "retendered": bucket["retendered"],
                "rework_rate_pct": round((bucket["cancelled"] + bucket["retendered"])
                                         / tenders * 100, 1) if tenders else 0,
                "tenders_with_bids": with_bids,
                "single_bidder": bucket["single_bidder"],
                "single_bidder_pct": round(bucket["single_bidder"] / with_bids * 100, 1)
                                     if with_bids else "",
                "documents_retrieved": bucket["documents"],
                "documents_with_text": bucket["documents_with_text"],
                "tenders_with_readable_docs": bucket["tenders_with_text"],
                "doc_coverage_pct": round(bucket["tenders_with_text"] / tenders * 100, 1)
                                    if tenders else 0,
                "maintenance_pct": round(bucket["modes"]["maintenance"] / tenders * 100, 1)
                                   if tenders else 0,
                "hired_capacity_pct": round(bucket["modes"]["hired_capacity"] / tenders * 100, 1)
                                      if tenders else 0,
                "recalled_pct": round(bucket["modes"]["recalled"] / tenders * 100, 1)
                                if tenders else 0,
                "top_year": bucket["years"].most_common(1)[0][0] if bucket["years"] else "",
                "top_value_band": bucket["bands"].most_common(1)[0][0] if bucket["bands"] else "",
                "dominant_scope": bucket["scopes"].most_common(1)[0][0] if bucket["scopes"] else "",
            })
        # Readable first: a segment can only be analysed from documents if it has some.
        rows_out.sort(key=lambda r: (-r["tenders_with_readable_docs"], -r["tenders"]))
        return rows_out

    records = build_profile(segments, "department")
    unit_records = build_profile(units, "unit")

    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "segment_profile.csv"
    with open(target, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)
    unit_target = OUT / "unit_profile.csv"
    with open(unit_target, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(unit_records[0].keys()))
        writer.writeheader()
        writer.writerows(unit_records)

    print(f"{len(records):,} segments across "
          f"{len({r['department'] for r in records})} departments and "
          f"{len({r['component'] for r in records})} work components; "
          f"{len(unit_records):,} unit segments across "
          f"{len({r['unit'] for r in unit_records})} leaf offices\n")
    print(f"{'department':30}{'component':14}{'tend':>6}{'readable':>9}{'cov%':>6}"
          f"{'1-bid%':>8}{'rework%':>8}{'value (cr)':>12}")
    for record in records[:18]:
        crore = record["contract_value_inr"] / 10_000_000
        print(f"  {record['department'][:28]:28}{record['component'][:12]:14}"
              f"{record['tenders']:>6,}{record['tenders_with_readable_docs']:>9,}"
              f"{record['doc_coverage_pct']:>6.0f}"
              f"{str(record['single_bidder_pct']):>8}{record['rework_rate_pct']:>8.1f}"
              f"{crore:>12,.1f}")
    print(f"\nwrote {target}\n      {unit_target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
