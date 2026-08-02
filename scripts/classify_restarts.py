#!/usr/bin/env python3
"""Classify WHY tenders restarted, from the clauses mined out of the documents.

Nothing in the structured data explains why any of the 6,198 multi-tender chains
restarted. The mined corpus does — but the raw clause extractor over-matches, and an
earlier report built on it published a 39.7% "unclassified" rate that was really two
defects in the pipeline, not a property of the documents:

  FALSE POSITIVES. The extractor anchors on "...cancelled..." and catches the
  boilerplate WARNING in award letters — "otherwise your tender will be cancelled and
  you will be debarred for one year". That is a threat addressed to a bidder about the
  future, not a record of a restart that happened. Around half the unclassified pile
  was this one sentence in OCR-mangled variants. Dropped here, with the count reported,
  because a warning about cancellation is not evidence of a cancellation.

  OCR DAMAGE. The clauses come from scanned letters: "admin1strat1ve feásons",
  "debaned", "porrizipation". Classification runs on a normalised copy (digits
  substituted back to letters inside words, accents stripped) while the VERBATIM
  clause is preserved in the output — the normalisation is for matching only and is
  never published as what the document says.

Output: build/mined/restart_reasons.csv, one row per (document, tender), carrying the
verbatim clause, its SHA-256, the category, and the matched phrase so every
classification can be checked against the page it came from.
"""
from __future__ import annotations

import csv
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parent.parent
FACTS = ROOT / "build" / "mined" / "document_facts.csv"
OUT = ROOT / "build" / "mined" / "restart_reasons.csv"

# A warning addressed to the bidder about what WILL happen is not a restart record.
WARNING = re.compile(
    r"\byour?\b|youwill|iseyour|debar|deban|debat|failing\s+which|"
    r"shall\s+be\s+forfeited|liable", re.I)

# Order matters: the first match wins, so the specific reasons come before the broad
# administrative bucket, and "no bid" outranks "technical" when a clause carries both.
CATEGORIES = [
    ("no_bid",
     re.compile(r"no\s+bid|non[-\s]?participat|no\s+response|single\s+bid|"
                r"lack\s+of\s+(bid|competition)|no\s+(tender|offer)\s+receiv|"
                r"poor\s+response|less\s+(than\s+)?(three|3|two|2)\s+bid|"
                r"insufficient\s+bidder|sufficient\s+bidders|zero\s+agenc|"
                r"(one|1|single|only)\s+(agency|firm|tender|bid)\s+(being\s+)?"
                r"(receiv|particip)|agenc(y|ies)\s+participated|"
                r"min(imum)?\s+bids?\s+not|bids?\s+not\s+receiv|"
                r"(bidder|tenderer)s?\s+(are\s+)?not\s+present|"
                r"are\s+not\s+present|not\s+present\W+tenders?|"
                r"not\s+receiv\w*\s+(of\s+)?(the\s+)?min|"
                r"sufficient\s+bids?\s+(not\s+)?found|single\s+tender", re.I)),
    ("error_in_tender",
     re.compile(r"error|mistake|wrong|inadverten|typograph|incorrect", re.I)),
    ("price",
     re.compile(r"rates?\s+(are|were|received|quoted|being)?\s*(on\s+)?higher|"
                r"higher\s+side|abnormally|budget|\bL-?1\b.*withdr|price", re.I)),
    ("technical_or_qualification",
     re.compile(r"technical|qualif|eligib|specification|criteria|"
                r"document(s)?\s+(not|in)complete", re.I)),
    ("validity_expired",
     re.compile(r"validity|expir|time\s+barred", re.I)),
    ("scope_changed",
     re.compile(r"scope|revised\s+(estimate|dnit|drawing)|"
                r"change\s+in\s+(site|design|dnit)|\bdnit\b.{0,30}(chang|revis)", re.I)),
    ("administrative",
     re.compile(r"administra?t\w*|admin\w*\s+reason|competent\s+authority|"
                r"higher\s+authorit|order\s+of\s+(the\s+)?\w+|approval|policy|"
                r"direction|department(al)?\s+(reason|order)", re.I)),
]


def normalise(value: str) -> str:
    """Undo the common OCR substitutions FOR MATCHING ONLY: digits standing in for
    letters inside words (admin1strat1ve, 0rder), and accented glyphs (feásons)."""
    text = unicodedata.normalize("NFKD", value)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))

    def deocr(match: re.Match) -> str:
        return (match.group(0).replace("1", "i").replace("0", "o")
                .replace("3", "e").replace("5", "s"))

    # Only inside alphabetic context — never touch standalone numbers or IDs.
    return re.sub(r"(?<=[a-zA-Z])[1035](?=[a-zA-Z])", lambda m: deocr(m), text)


def main() -> int:
    if not FACTS.exists():
        sys.exit(f"{FACTS} missing; run extract_documents.py / mine_documents.py first")

    rows_out = []
    tally: Counter = Counter()
    warnings_dropped = 0
    with open(FACTS, newline="", encoding="utf-8", errors="replace") as handle:
        for row in csv.DictReader(handle):
            clause = (row.get("restart_clause") or "").strip()
            if not clause:
                continue
            reason = (row.get("restart_reason") or "").strip()
            haystack = normalise(f"{clause} {reason}")
            if WARNING.search(haystack):
                warnings_dropped += 1
                continue
            category, phrase = "unclassified", ""
            for name, rx in CATEGORIES:
                hit = rx.search(haystack)
                if hit:
                    category, phrase = name, hit.group(0)
                    break
            tally[category] += 1
            rows_out.append({
                "sha256": row.get("sha256", ""),
                "stage": row.get("stage", ""),
                "tender_id_primary": row.get("tender_id_primary", ""),
                "category": category,
                "matched_phrase": phrase,
                "restart_clause_verbatim": clause,
                "restart_reason_verbatim": reason,
            })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows_out[0].keys()))
        writer.writeheader()
        writer.writerows(rows_out)

    total = len(rows_out)
    print(f"restart clauses kept   {total:,}")
    print(f"bidder warnings dropped {warnings_dropped:,} "
          f"(boilerplate threats, not restart records)")
    for name, count in tally.most_common():
        print(f"  {name:26} {count:>5}  {count / total * 100:.1f}%")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
