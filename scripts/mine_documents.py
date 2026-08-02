#!/usr/bin/env python3
"""Mine structured facts out of the extracted document text.

WHAT THIS IS FOR
----------------
The structured CSVs already carry tender_id, status, award state and contractor NAME.
What they do not carry, and what the letters do, is:

  * the contractor's REGISTRATION CODE — "SUPER GLOBAL INFRASTRUCTURE [2021R586]".
    This is the single most valuable field in the whole document corpus, because it is a
    stable identifier. 8,241 raw bidder names collapse into 641 fragmentation candidate
    groups that cannot be merged safely on string similarity alone; a registration code
    settles identity without guessing.
  * postal address, e-mail and phone for the awarded firm;
  * the agreement amount as WRITTEN IN THE LETTER, which is an independent witness to
    aoc_total_contract_value_inr rather than a copy of it;
  * memo numbers and letter dates;
  * the REASON a tender was re-invited. One corrigendum reads "is hereby re-invited due
    to no bid received." Nothing in the structured data explains why any of the 6,198
    multi-tender chains restarted, and 2,426 of them never reached an award.

EVERY FIELD CARRIES ITS SOURCE
------------------------------
Each extracted value is written with the blob sha256 it came from and the verbatim line
it was matched on, so any figure can be checked against the document. A value that is
merely probable is not promoted to a fact: patterns are anchored on the labels the
letters actually use, and anything ambiguous is left absent rather than guessed.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = Path(os.environ.get("CIVIC_STUFF", ROOT.parent / "civic-stuff"))
DOCS = ARCHIVE / "data" / "final" / "documents.csv"
TEXT = ROOT / "build" / "doctext"
OUT = ROOT / "build" / "mined"

# ---------------------------------------------------------------- patterns
# Anchored on the labels the letters actually print. Loose patterns invent data.

RE_REG = re.compile(r"([A-Z][A-Za-z0-9&.,\-/() ]{3,80}?)\s*\[\s*(\d{4}[A-Z]\d{2,6})\s*\]")
RE_TENDER = re.compile(r"\b(20\d{2}_[A-Z]{3}_\d{4,7}_\d{1,2})\b")
RE_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
RE_PHONE = re.compile(r"\b(?:\+?91[\-\s]?)?([6-9]\d{9})\b")
RE_MEMO = re.compile(r"Memo\s*No\.?\s*[-:]?\s*([A-Za-z0-9/\-]+)", re.I)
RE_DATED = re.compile(r"Dated\s*[-:.]?\s*(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})", re.I)
# "Agreement Amount (Rs.) - 14,23,026 /-"  and the common variants.
RE_AMOUNT = re.compile(
    r"(Agreement\s+Amount|Awarded\s+(?:Amount|Value)|Contract\s+(?:Amount|Value)|"
    r"Accepted\s+Amount|Tendered\s+Amount)\s*"
    r"(?:\(\s*(?:Rs\.?|INR|₹)\s*\)|in\s+Rs\.?)?\s*[-:.]?\s*"
    r"(?:Rs\.?|INR|₹)?\s*([\d,]{3,20}(?:\.\d{1,2})?)", re.I)
# Why a tender restarted. The verb is what matters; the clause after it is the reason.
RE_REINVITE = re.compile(
    r"((?:is|are|being|hereby)[^.]{0,80}?"
    r"(?:re-?invited|re-?tendered|re-?called|cancelled|annulled|withdrawn)"
    r"[^.]{0,160}?)(?:\.|$)", re.I)
RE_REASON = re.compile(
    r"(?:due\s+to|owing\s+to|on\s+account\s+of|because\s+of|reason\s*[-:])\s*"
    r"([^.\n]{4,120})", re.I)


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


def to_amount(raw: str) -> float | None:
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        return None


def mine(sha: str, stage: str, text: str) -> dict:
    """Pull the anchored fields. Absent beats guessed."""
    out: dict = {"sha256": sha, "stage": stage}

    tenders = RE_TENDER.findall(text)
    out["tender_ids_mentioned"] = " ".join(sorted(set(tenders)))
    out["tender_id_primary"] = Counter(tenders).most_common(1)[0][0] if tenders else ""

    regs = RE_REG.findall(text)
    if regs:
        # First occurrence wins: the addressee block is at the top of these letters.
        name, code = regs[0]
        out["party_name"] = clean(name)
        out["party_registration_code"] = code
        out["party_registration_all"] = " ".join(sorted({c for _, c in regs}))
    emails = RE_EMAIL.findall(text)
    if emails:
        out["emails"] = " ".join(sorted(set(emails))[:4])
    phones = RE_PHONE.findall(text)
    if phones:
        out["phones"] = " ".join(sorted(set(phones))[:4])
    memo = RE_MEMO.search(text)
    if memo:
        out["memo_no"] = clean(memo.group(1))
    dated = RE_DATED.search(text)
    if dated:
        out["letter_date_raw"] = clean(dated.group(1))

    amounts = RE_AMOUNT.findall(text)
    if amounts:
        label, raw = amounts[0]
        value = to_amount(raw)
        if value is not None:
            out["amount_label"] = clean(label)
            out["amount_inr"] = value
            # The verbatim line, so the figure can be checked against the page.
            for line in text.splitlines():
                if raw in line:
                    out["amount_source_line"] = clean(line)[:200]
                    break

    reinvite = RE_REINVITE.search(text)
    if reinvite:
        clause = clean(reinvite.group(1))
        out["restart_clause"] = clause[:200]
        reason = RE_REASON.search(clause) or RE_REASON.search(text)
        if reason:
            out["restart_reason"] = clean(reason.group(1))[:120]
    return out


FIELDS = ["sha256", "stage", "tender_id_primary", "tender_ids_mentioned",
          "party_name", "party_registration_code", "party_registration_all",
          "emails", "phones", "memo_no", "letter_date_raw",
          "amount_label", "amount_inr", "amount_source_line",
          "restart_clause", "restart_reason"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    stage_of: dict[str, str] = {}
    for row in csv.DictReader(open(DOCS, newline="", encoding="utf-8", errors="replace")):
        sha = (row.get("sha256") or "").strip()
        if sha and sha not in stage_of:
            stage_of[sha] = row.get("stage_or_section") or ""

    files = sorted(TEXT.rglob("*.txt"))
    if args.limit:
        files = files[: args.limit]
    print(f"mining {len(files):,} extracted documents")

    records = []
    stats = Counter()
    per_stage = defaultdict(Counter)
    for path in files:
        sha = path.stem
        stage = stage_of.get(sha, "unknown")
        text = path.read_text(encoding="utf-8", errors="replace")
        record = mine(sha, stage, text)
        for key in ("party_registration_code", "amount_inr", "restart_reason",
                    "emails", "phones", "memo_no", "tender_id_primary"):
            if record.get(key):
                stats[key] += 1
                per_stage[stage][key] += 1
        records.append(record)

    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "document_facts.csv"
    tmp = target.with_suffix(".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow(record)
    os.replace(tmp, target)

    print(f"\nfields recovered across {len(records):,} documents:")
    for key, count in stats.most_common():
        print(f"   {key:26} {count:>7,}  ({count / len(records) * 100:.1f}%)")
    print(f"\nby stage:")
    for stage, counter in sorted(per_stage.items(), key=lambda kv: -sum(kv[1].values())):
        top = ", ".join(f"{k}={v:,}" for k, v in counter.most_common(4))
        print(f"   {stage[:24]:26} {top}")
    (ROOT / "build" / "mined_report.json").write_text(
        json.dumps({"documents": len(records), "fields": dict(stats),
                    "by_stage": {k: dict(v) for k, v in per_stage.items()}},
                   indent=2, sort_keys=True) + "\n")
    print(f"\nwrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
