#!/usr/bin/env python3
"""Detect the lakh-denomination bug in published contract values, and correct only
what an award letter actually evidences.

THE BUG
-------
`tenders.aoc_total_contract_value_inr` sometimes carries a LAKH-denominated figure in a
rupee-denominated column. Worked example, 2025_HRY_444909_1 — upgrading a hospital HVAC
system in Sector-10 Gurugram:

    tender_value_inr               68,526,021     the estimate, in rupees
    aoc_total_contract_value_inr        685.26    the estimate / 100,000
    Letter of Award            7,03,27,583        "Agreement Amount (Rs.)"

The portal publishes ₹685 for a ₹7.03 crore contract. Across the 103 controlling awards
carrying this signature the published total is ₹6,082 against estimates of
₹601,689,207 — the headline is understated by roughly ₹60.2 crore, or 0.72%.

The aggregate barely moves. The individual pages are badly wrong, and that is what this
fixes: a citizen who opens one of those tenders currently reads a nonsense figure.

WHAT MAY AND MAY NOT BE CORRECTED
---------------------------------
Only an AWARD LETTER may correct an award value.

  * 38 of the 103 have a letter carrying an explicit "Agreement Amount". That figure IS
    the contract value, from the primary document, and it replaces the portal figure —
    with the portal figure still shown beside it, the document named, and its SHA-256
    printed so the correction can be checked.

  * The remaining 65 have no letter in this archive. They are FLAGGED and nothing is
    substituted. The estimate is shown only as the reason the value is implausible —
    because the published figure equals it divided by 100,000 — and never as the award
    value. An estimate is not an award, and putting one in an award column to make a
    total look complete would be the same class of error as the bug being fixed.

Nothing is overwritten in the archive. This emits a correction layer that the package
builder attaches to the affected tenders.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = Path(os.environ.get("CIVIC_STUFF", ROOT.parent / "civic-stuff"))
FINAL = ARCHIVE / "data" / "final"
DERIVED = ARCHIVE / "data" / "derived"
MINED = ROOT / "build" / "mined" / "document_facts.csv"
OUT_JSON = ROOT / "public" / "data" / "value-corrections.json"
OUT_CSV = ROOT / "build" / "value_corrections.csv"

# The signature. Deliberately narrow: a small award value alone is not evidence of the
# bug — some contracts really are small. What identifies it is a small award value whose
# ratio to the tender's OWN estimate sits at the 1e5 boundary. The window is wide enough
# to absorb rounding in the published estimate and narrow enough to exclude a genuine
# award that happens to be far below its estimate.
RATIO_LOW, RATIO_HIGH = 50_000, 200_000
AWARD_CEILING = 1_000


def rows(path: Path):
    with open(path, newline="", encoding="utf-8", errors="replace") as handle:
        yield from csv.DictReader(handle)


def number(value: str) -> float | None:
    try:
        return float((value or "").strip())
    except (TypeError, ValueError):
        return None


def main() -> int:
    tenders = {r["tender_id"]: r for r in rows(FINAL / "tenders.csv")}
    chains = {r["tender_id"]: r for r in rows(DERIVED / "procurement_chains.csv")}
    scope = {r["tender_id"]: r["scope_classification"]
             for r in rows(FINAL / "gurugram_scope.csv")}

    def controlling(tender_id: str) -> bool:
        chain = chains.get(tender_id)
        if not chain or chain["award_state"] != "AWARD_CONFIRMED":
            return False
        if chain.get("chain_is_ambiguous") == "true":
            return False
        terminal = chain.get("terminal_tender_id", "")
        return not terminal or terminal == tender_id

    # Letter evidence, keyed by tender. Keep the LARGEST agreement amount seen for a
    # tender: a letter may quote several figures (construction, O&M, security deposit)
    # and the agreement total is the largest of them. The source line is retained so the
    # choice is checkable rather than asserted.
    letters: dict[str, dict] = {}
    if MINED.exists():
        for record in rows(MINED):
            tender_id = record.get("tender_id_primary") or ""
            amount = number(record.get("amount_inr", ""))
            if not tender_id or amount is None:
                continue
            best = letters.get(tender_id)
            if best is None or amount > best["amount"]:
                letters[tender_id] = {
                    "amount": amount,
                    "sha256": record.get("sha256", ""),
                    "label": record.get("amount_label", ""),
                    "line": record.get("amount_source_line", ""),
                    "stage": record.get("stage", ""),
                }

    corrections = []
    for tender_id, tender in tenders.items():
        published = number(tender.get("aoc_total_contract_value_inr", ""))
        estimate = number(tender.get("tender_value_inr", ""))
        if published is None or published <= 0 or published >= AWARD_CEILING:
            continue
        if not estimate or estimate <= 0:
            continue
        ratio = estimate / published
        if not (RATIO_LOW <= ratio <= RATIO_HIGH):
            continue

        evidence = letters.get(tender_id)
        record = {
            "tender_id": tender_id,
            "scope": scope.get(tender_id, ""),
            "is_controlling_award": "true" if controlling(tender_id) else "false",
            "published_value_inr": published,
            "estimate_inr": estimate,
            "estimate_over_published": round(ratio, 1),
            "work_description": (tender.get("work_description") or "")[:180],
        }
        if evidence and evidence["amount"] > published * 1000:
            # The letter must be materially larger, or it is not evidence of this bug.
            record.update({
                "status": "corrected_from_award_letter",
                "corrected_value_inr": evidence["amount"],
                "evidence_sha256": evidence["sha256"],
                "evidence_stage": evidence["stage"],
                "evidence_label": evidence["label"],
                "evidence_line": evidence["line"],
            })
        else:
            record.update({
                "status": "implausible_no_letter",
                "corrected_value_inr": "",
                "evidence_sha256": "",
                "evidence_stage": "",
                "evidence_label": "",
                "evidence_line": "",
            })
        corrections.append(record)

    corrections.sort(key=lambda r: (r["status"], r["tender_id"]))
    fields = ["tender_id", "scope", "is_controlling_award", "status",
              "published_value_inr", "corrected_value_inr", "estimate_inr",
              "estimate_over_published", "evidence_sha256", "evidence_stage",
              "evidence_label", "evidence_line", "work_description"]
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in corrections:
            writer.writerow(record)

    corrected = [r for r in corrections if r["status"] == "corrected_from_award_letter"]
    flagged = [r for r in corrections if r["status"] == "implausible_no_letter"]
    ctrl_corrected = [r for r in corrected if r["is_controlling_award"] == "true"]
    ctrl_flagged = [r for r in flagged if r["is_controlling_award"] == "true"]

    # The published headline, and what it becomes once ONLY the letter-evidenced awards
    # are corrected. The flagged 65 contribute their published value unchanged — their
    # true value is not in this archive and an estimate may not stand in for it.
    controlling_ids = [t for t in tenders
                       if controlling(t) and scope.get(t) == "confirmed_gurugram"]
    baseline = sum(v for t in controlling_ids
                   if (v := number(tenders[t].get("aoc_total_contract_value_inr", ""))) is not None)
    fix = {r["tender_id"]: r["corrected_value_inr"] for r in ctrl_corrected
           if scope.get(r["tender_id"]) == "confirmed_gurugram"}
    adjusted = sum(fix.get(t, number(tenders[t].get("aoc_total_contract_value_inr", "")) or 0)
                   for t in controlling_ids)

    payload = {
        "datasetVersion": next(iter(chains.values())).get("dataset_version", ""),
        "rule": {
            "name": "lakh_denominated_award_value",
            "test": (f"published award value < {AWARD_CEILING} AND "
                     f"{RATIO_LOW} <= (estimate / published) <= {RATIO_HIGH}"),
            "reason": ("The portal stores a lakh-denominated figure in a rupee column, so "
                       "the published award equals the estimate divided by 100,000."),
            "correctionPolicy": (
                "Only an award letter may correct an award value. Where a letter states "
                "an agreement amount it replaces the published figure and the document "
                "SHA-256 is printed. Where no letter exists the value is flagged and "
                "NOTHING is substituted: an estimate is not an award value."),
        },
        "counts": {
            "detected": len(corrections),
            "correctedFromLetter": len(corrected),
            "flaggedNoLetter": len(flagged),
            "controllingCorrected": len(ctrl_corrected),
            "controllingFlagged": len(ctrl_flagged),
        },
        "headline": {
            "publishedControllingContractValue": round(baseline, 2),
            "afterLetterCorrections": round(adjusted, 2),
            "differenceInr": round(adjusted - baseline, 2),
            "note": ("Only the letter-evidenced awards move this figure. The flagged "
                     "tenders keep their published value because their true award value "
                     "is not established by this archive."),
        },
        "tenders": {r["tender_id"]: {
            "status": r["status"],
            "publishedValueInr": r["published_value_inr"],
            "correctedValueInr": r["corrected_value_inr"] or None,
            "estimateInr": r["estimate_inr"],
            "estimateOverPublished": r["estimate_over_published"],
            "evidenceSha256": r["evidence_sha256"] or None,
            "evidenceStage": r["evidence_stage"] or None,
            "evidenceLine": r["evidence_line"] or None,
        } for r in corrections},
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    print(f"detected {len(corrections):,} tenders carrying the lakh signature")
    print(f"   corrected from an award letter : {len(corrected):,} "
          f"({len(ctrl_corrected):,} controlling)")
    print(f"   flagged, no letter available   : {len(flagged):,} "
          f"({len(ctrl_flagged):,} controlling)")
    print(f"\nconfirmed-Gurugram controlling contract value")
    print(f"   published            Rs {baseline:>20,.2f}")
    print(f"   after corrections    Rs {adjusted:>20,.2f}")
    print(f"   difference           Rs {adjusted - baseline:>20,.2f} "
          f"({(adjusted - baseline) / baseline * 100:+.3f}%)")
    print(f"\nwrote {OUT_JSON}\n      {OUT_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
