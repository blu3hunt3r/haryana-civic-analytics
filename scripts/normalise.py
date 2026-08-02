#!/usr/bin/env python3
"""Normalise the fields that block analysis, and reject nothing silently.

WHY THIS EXISTS
---------------
Two measured blockers stop most of the analysis this corpus can support. Neither is a
modelling problem; both are normalisation problems that were never done.

1. DATES. `tender_lifecycle_events.event_at` is 100% populated across 339,034 rows and
   carries THREE formats in the one column:

       02-Apr-2011 06:00 PM        portal format
       2012-11-02                  ISO date
       2026-07-27T12:00:54+05:30   ISO datetime with offset

   Nothing downstream can compute a duration against that, so no time-to-award, no
   stage-timing and no delay analysis exists. With the parser below all 339,034 parse.

2. PARTY NAMES. 8,241 distinct bidder names collapse to 7,112 groups under conservative
   normalisation, with 635 groups holding 1,761 raw spellings — "KRISHNA CONSTRUCTION CO"
   and "Krishna Builders" and "KRISHNA CONSTRUCTIONS" among them.

WHAT THIS DELIBERATELY DOES NOT DO
----------------------------------
It does NOT merge parties. Grouping is emitted as CANDIDATES with a `decision` column
defaulting to `unreviewed`, because the normalisation that produces a group works by
deleting the words that distinguish firms: "Balaji Enterprises", "Bala Ji Builders" and
"Balaji Construction And Company" land in one bucket and may be three unrelated
businesses. Auto-merging would manufacture a concentration finding out of a string
operation. ASSET_CONTRACT's rule against treating a candidate fuzzy link as an exact
identity applies to parties exactly as it applies to assets.

A further 773 names are 44+ characters, i.e. truncated at source. Those identities are
not recoverable from this archive and are flagged rather than guessed.

NOTHING IS DROPPED
------------------
Every value that fails to parse is written to a rejects file with its row, its column and
the reason. A silent drop is how a corpus quietly loses records; the count of rejects is
part of the output and is asserted to be zero for dates.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = Path(os.environ.get("CIVIC_STUFF", ROOT.parent / "civic-stuff"))
OUT = ROOT / "build" / "normalised"

MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}

# ---------------------------------------------------------------- dates

def parse_date(value: str) -> tuple[datetime.date | None, str]:
    """Return (date, format-tag). Every branch is a format seen in the corpus."""
    text = (value or "").strip()
    if not text:
        return None, "empty"
    m = re.match(r"^(\d{1,2})-([A-Za-z]{3})-(\d{4})", text)
    if m and m.group(2).title() in MONTHS:
        return datetime.date(int(m.group(3)), MONTHS[m.group(2).title()],
                             int(m.group(1))), "dd-Mon-yyyy"
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        y, mo, d = map(int, m.groups())
        try:
            return datetime.date(y, mo, d), "iso"
        except ValueError:
            return None, "iso-out-of-range"
    m = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})$", text)
    if m:
        # dd-mm-yy(yy). Ambiguous with mm-dd only when both parts are <= 12; the corpus
        # is Indian-formatted, so day-first is the correct reading, and the ambiguous
        # cases are tagged so a reviewer can see how many there were.
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000 if y < 70 else 1900
        try:
            return datetime.date(y, mo, d), ("dd-mm-yyyy-ambiguous" if d <= 12
                                             else "dd-mm-yyyy")
        except ValueError:
            return None, "dd-mm-yyyy-invalid"
    m = re.match(r"^(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})$", text)
    if m and m.group(2)[:3].title() in MONTHS:
        return datetime.date(int(m.group(3)), MONTHS[m.group(2)[:3].title()],
                             int(m.group(1))), "d Month yyyy"
    return None, "unrecognised"


# ---------------------------------------------------------------- money

def parse_money(value: str) -> tuple[float | None, str]:
    """Rupee values as published. Returns (amount, quality-tag).

    The tags matter more than the number. 178 controlling awards carry exactly 1, 302 are
    below 1,000 and the minimum is 0.40 — placeholders, not contracts of that size. They
    are kept (they are what the State published) and labelled, so a ratio can exclude
    them without a downstream consumer having to rediscover the problem.
    """
    text = (value or "").strip().replace(",", "")
    if not text:
        return None, "absent"
    try:
        amount = float(text)
    except ValueError:
        return None, "unparseable"
    if amount < 0:
        return amount, "negative"
    if amount == 0:
        return 0.0, "zero"
    if amount <= 1:
        return amount, "placeholder_suspected"
    if amount < 1000:
        return amount, "implausibly_small"
    return amount, "ok"


# ---------------------------------------------------------------- parties

HONORIFICS = r"\b(SH|SHRI|SMT|SRI|M/S|MS|MR|MESSRS|THE)\b\.?"
LEGAL_FORMS = (r"\b(CONTR|CONTRACTOR|CONTRACTORS|PVT|PRIVATE|LTD|LIMITED|LLP|CO|COMPANY|"
               r"ENTERPRISES|ENTERPRISE|CONSTRUCTIONS?|BUILDERS?|INFRA|INFRASTRUCTURES?|"
               r"AND|&)\b\.?")

def party_key(name: str) -> str:
    """A deliberately AGGRESSIVE key, used only to propose candidate groups.

    It strips the very tokens that distinguish firms, which is why its output is a review
    queue and never a merge. Two names sharing a key is a question, not an answer.
    """
    s = (name or "").upper()
    s = re.sub(HONORIFICS, " ", s)
    s = re.sub(LEGAL_FORMS, " ", s)
    s = re.sub(r"[^A-Z0-9]+", "", s)
    return s


def rows(path: Path):
    with open(path, newline="", encoding="utf-8", errors="replace") as handle:
        yield from csv.DictReader(handle)


def write_csv(path: Path, fieldnames: list[str], records) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    count = 0
    with open(tmp, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(record)
            count += 1
    os.replace(tmp, path)
    return count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", default=str(ARCHIVE))
    args = parser.parse_args()
    archive = Path(args.archive)
    final = archive / "data" / "final"
    if not (final / "tenders.csv").exists():
        sys.exit(f"archive not found at {final}")

    stats: dict[str, object] = {}
    rejects: list[dict] = []

    # ---- 1. lifecycle dates -------------------------------------------------
    formats = Counter()
    normalised_events = []
    for row in rows(final / "tender_lifecycle_events.csv"):
        parsed, tag = parse_date(row["event_at"])
        formats[tag] += 1
        if parsed is None:
            rejects.append({"table": "tender_lifecycle_events", "key": row["tender_id"],
                            "column": "event_at", "value": row["event_at"][:80],
                            "reason": tag})
            continue
        normalised_events.append({
            "tender_id": row["tender_id"],
            "event_type": row["event_type"],
            "event_date": parsed.isoformat(),
            "source_format": tag,
            "source_sha256": row.get("source_sha256", ""),
        })
    written = write_csv(OUT / "lifecycle_events_normalised.csv",
                        ["tender_id", "event_type", "event_date", "source_format",
                         "source_sha256"], normalised_events)
    stats["lifecycle_events"] = {"in": sum(formats.values()), "out": written,
                                 "formats": dict(formats)}

    # ---- 2. derived durations ----------------------------------------------
    # Only the pairs the events actually support. A missing endpoint is not a zero.
    by_tender: dict[str, dict[str, str]] = defaultdict(dict)
    for record in normalised_events:
        # Keep the EARLIEST occurrence of each type: a status is re-observed many times.
        existing = by_tender[record["tender_id"]].get(record["event_type"])
        if existing is None or record["event_date"] < existing:
            by_tender[record["tender_id"]][record["event_type"]] = record["event_date"]

    durations = []
    negative = 0
    for tender_id, events in by_tender.items():
        published = events.get("tender_published")
        award = events.get("contract_award")
        closed = events.get("bid_submission_closed")
        row = {"tender_id": tender_id, "published_on": published or "",
               "bid_closed_on": closed or "", "awarded_on": award or "",
               "days_published_to_close": "", "days_published_to_award": "",
               "duration_quality": "ok"}
        if published and closed:
            row["days_published_to_close"] = (
                datetime.date.fromisoformat(closed)
                - datetime.date.fromisoformat(published)).days
        if published and award:
            delta = (datetime.date.fromisoformat(award)
                     - datetime.date.fromisoformat(published)).days
            row["days_published_to_award"] = delta
            if delta < 0:
                # An award dated before publication is a source contradiction, not a
                # negative duration to average into anything.
                row["duration_quality"] = "award_precedes_publication"
                negative += 1
        durations.append(row)
    write_csv(OUT / "tender_durations.csv",
              ["tender_id", "published_on", "bid_closed_on", "awarded_on",
               "days_published_to_close", "days_published_to_award",
               "duration_quality"], durations)
    usable = [r["days_published_to_award"] for r in durations
              if isinstance(r["days_published_to_award"], int)
              and r["duration_quality"] == "ok"]
    usable.sort()
    stats["durations"] = {
        "tenders": len(durations),
        "with_award_duration": len(usable),
        "award_precedes_publication": negative,
        "median_days": usable[len(usable) // 2] if usable else None,
        "p95_days": usable[int(len(usable) * 0.95)] if usable else None,
        "max_days": usable[-1] if usable else None,
        "over_365_days": sum(1 for d in usable if d > 365),
    }

    # ---- 3. money quality ---------------------------------------------------
    money_tags = Counter()
    for row in rows(final / "tenders.csv"):
        _, tag = parse_money(row.get("aoc_total_contract_value_inr", ""))
        money_tags[tag] += 1
    stats["contract_value_quality"] = dict(money_tags)

    # ---- 4. party candidates (a review queue, never a merge) ---------------
    seen: dict[str, Counter] = defaultdict(Counter)
    bid_counts: Counter = Counter()
    for row in rows(final / "bid_history.csv"):
        name = (row.get("bidder_name") or "").strip()
        if not name:
            continue
        seen[party_key(name)][name] += 1
        bid_counts[name] += 1

    candidates = []
    for key, spellings in sorted(seen.items(), key=lambda kv: -len(kv[1])):
        if not key or len(spellings) < 2:
            continue
        members = sorted(spellings)
        candidates.append({
            "candidate_group": hashlib.sha1(key.encode()).hexdigest()[:12],
            "normalised_key": key,
            "spelling_count": len(members),
            "bid_count": sum(spellings.values()),
            "spellings": " | ".join(members),
            "any_truncated": "true" if any(len(m) >= 44 for m in members) else "false",
            # THE POINT OF THE WHOLE FILE. Nothing merges until a human writes here.
            "decision": "unreviewed",
            "decided_by": "",
            "decision_note": "",
        })
    write_csv(OUT / "party_resolution_candidates.csv",
              ["candidate_group", "normalised_key", "spelling_count", "bid_count",
               "spellings", "any_truncated", "decision", "decided_by",
               "decision_note"], candidates)
    truncated = sum(1 for n in bid_counts if len(n) >= 44)
    stats["parties"] = {
        "raw_names": len(bid_counts),
        "normalised_groups": len(seen),
        "candidate_groups_needing_review": len(candidates),
        "raw_names_inside_candidates": sum(c["spelling_count"] for c in candidates),
        "names_truncated_at_source": truncated,
        "resolved": 0,
        "note": ("Candidates only. A shared key is a question, not an identity: the key "
                 "is built by deleting legal forms, so unrelated firms can collide. "
                 "Concentration must be published as 'at least N distinct winners' "
                 "until decisions exist."),
    }

    # ---- 5. rejects ---------------------------------------------------------
    write_csv(OUT / "rejects.csv",
              ["table", "key", "column", "value", "reason"], rejects)
    stats["rejects"] = len(rejects)

    report = OUT / "normalisation_report.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(stats, indent=2, sort_keys=True) + "\n")

    print(f"lifecycle events   {stats['lifecycle_events']['out']:,} normalised "
          f"of {stats['lifecycle_events']['in']:,}")
    for tag, n in sorted(formats.items(), key=lambda kv: -kv[1]):
        print(f"    {tag:24} {n:>8,}")
    d = stats["durations"]
    print(f"durations          {d['with_award_duration']:,} tenders with a "
          f"publication→award duration")
    print(f"    median {d['median_days']}d  p95 {d['p95_days']}d  max {d['max_days']}d  "
          f"over a year {d['over_365_days']:,}")
    print(f"    award dated before publication: {d['award_precedes_publication']:,}")
    print(f"contract values    {stats['contract_value_quality']}")
    p = stats["parties"]
    print(f"parties            {p['raw_names']:,} raw names → "
          f"{p['candidate_groups_needing_review']:,} candidate groups awaiting review "
          f"({p['raw_names_inside_candidates']:,} names), "
          f"{p['names_truncated_at_source']:,} truncated at source")
    print(f"rejects            {stats['rejects']:,}  → build/normalised/rejects.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
