#!/usr/bin/env python3
"""Validate public analytics artifacts against the source archive.

The verifier fails closed: headline totals, scope separation, detail coverage,
document counts, contract-value semantics and source hashes must all reconcile.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
ROOT = Path(
    os.environ.get("CIVIC_DATA_ROOT", REPO.parent / "civic-stuff")
).resolve()
DATA = REPO / "public" / "data"


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Audit:
    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []

    def check(self, name: str, expected: Any, actual: Any) -> None:
        passed = expected == actual
        def serialisable(value: Any) -> Any:
            if isinstance(value, set):
                ordered = sorted(value)
                digest = hashlib.sha256(
                    "\n".join(ordered).encode("utf-8")
                ).hexdigest()
                return {"count": len(ordered), "sha256": digest}
            if isinstance(value, dict):
                return {
                    (
                        "|".join(map(str, key))
                        if isinstance(key, tuple)
                        else str(key)
                    ): serialisable(item)
                    for key, item in value.items()
                }
            if isinstance(value, tuple):
                return [serialisable(item) for item in value]
            return value
        self.checks.append(
            {
                "name": name,
                "passed": passed,
                "expected": serialisable(expected),
                "actual": serialisable(actual),
            }
        )
        if not passed:
            raise AssertionError(f"{name}: expected {expected!r}; got {actual!r}")

    def true(self, name: str, actual: bool, detail: Any = None) -> None:
        self.check(name, True, bool(actual))
        if detail is not None:
            self.checks[-1]["detail"] = detail


def main() -> None:
    audit = Audit()
    manifest = load_json(DATA / "manifest.json")
    overview = load_json(DATA / "overview.json")
    tenders = load_json(DATA / "tenders.json")

    source_tenders = read_csv(ROOT / "data/final/tenders.csv")
    source_scope = read_csv(ROOT / "data/final/gurugram_scope.csv")
    source_documents = read_csv(ROOT / "data/final/documents.csv")

    source_ids = [row["tender_id"] for row in source_tenders]
    public_ids = [row["id"] for row in tenders]
    audit.check("source_tender_ids_unique", len(source_ids), len(set(source_ids)))
    audit.check("public_tender_ids_unique", len(public_ids), len(set(public_ids)))
    audit.check("public_tender_count", len(source_ids), len(public_ids))
    audit.check("public_tender_id_set", set(source_ids), set(public_ids))

    source_scope_counts = Counter(row["scope_classification"] for row in source_scope)
    public_scope_counts = Counter(row["scope"] for row in tenders)
    audit.check(
        "scope_counts_reconcile",
        dict(source_scope_counts),
        dict(public_scope_counts),
    )
    audit.check(
        "overview_confirmed_count",
        source_scope_counts["confirmed_gurugram"],
        overview["headline"]["confirmedGurugram"],
    )
    audit.check(
        "overview_confirmed_plus_likely_count",
        source_scope_counts["confirmed_gurugram"]
        + source_scope_counts["likely_gurugram"],
        overview["headline"]["confirmedPlusLikelyGurugram"],
    )

    confirmed = [row for row in tenders if row["scope"] == "confirmed_gurugram"]
    audit.check(
        "overview_confirmed_awarded",
        sum(row["isAwarded"] for row in confirmed),
        overview["headline"]["confirmedAwarded"],
    )
    controlling_value = sum(
        (row["contractValue"] or 0)
        for row in confirmed
        if row["isControllingAward"]
    )
    audit.check(
        "overview_contract_value_uses_controlling_awards_only",
        controlling_value,
        overview["headline"]["confirmedControllingContractValue"],
    )
    audit.true(
        "cancelled_or_retendered_never_controlling_award",
        not any(
            row["isControllingAward"]
            for row in tenders
            if row["status"] in {"Cancelled", "Retender"}
        ),
    )
    audit.true(
        "statewide_not_in_confirmed_default",
        not any(
            row["scope"] == "statewide_multi_location" for row in confirmed
        ),
    )
    audit.check(
        "document_record_count",
        len(source_documents),
        sum(row["documentCount"] for row in tenders),
    )
    id_year_rows = [
        (row, re.match(r"^(20\d{2})_", row["id"]))
        for row in tenders
    ]
    audit.true(
        "analytics_year_uses_tender_id_prefix",
        all(
            not match or row["year"] == match.group(1)
            for row, match in id_year_rows
        ),
    )
    audit.true(
        "conflicted_portal_dates_never_supply_month",
        all(
            not row["publishedDateConflict"] or row["month"] is None
            for row in tenders
        ),
    )
    confirmed_conflicts = sum(
        row["publishedDateConflict"]
        for row in tenders
        if row["scope"] == "confirmed_gurugram"
    )
    audit.check(
        "overview_portal_date_conflict_count",
        confirmed_conflicts,
        overview["reviewFlags"]["portalPublishedDateConflictsWithTenderIdYear"],
    )
    district_geometry = load_json(DATA / "geo" / "haryana_districts.geojson")
    district_names = {
        feature["properties"]["dtname"]
        for feature in district_geometry["features"]
    }
    audit.check("haryana_district_geometry_count", 23, len(district_names))
    public_districts = {
        area["value"]
        for row in tenders
        for area in row["areas"]
        if area["level"] == "district"
    }
    audit.true(
        "all_district_links_resolve_to_geometry",
        public_districts <= district_names,
        sorted(public_districts - district_names),
    )
    expected_district_values = Counter()
    for row in tenders:
        districts = {
            area["value"]
            for area in row["areas"]
            if area["level"] == "district"
        }
        if (
            len(districts) == 1
            and row["isControllingAward"]
            and row["contractValue"] is not None
        ):
            district = next(iter(districts))
            expected_district_values[
                (row["scope"], district)
            ] += row["contractValue"]
    actual_district_values = {
        (area["scope"], area["value"]): area["contractValue"]
        for area in overview["areas"]
        if area["level"] == "district" and area["contractValue"]
    }
    audit.check(
        "district_contract_values_exclude_multi_district_duplication",
        dict(expected_district_values),
        actual_district_values,
    )

    detail_ids: set[str] = set()
    detail_document_count = 0
    for shard_path in sorted((DATA / "tender-details").glob("*.json")):
        shard = load_json(shard_path)
        audit.true(
            f"detail_shard_no_duplicate_{shard_path.stem}",
            detail_ids.isdisjoint(shard),
        )
        detail_ids.update(shard)
        detail_document_count += sum(len(row["documents"]) for row in shard.values())
    audit.check("detail_shard_count", manifest["records"]["detailShards"], len(list((DATA / "tender-details").glob("*.json"))))
    audit.check("detail_tender_coverage", set(public_ids), detail_ids)
    audit.check("detail_document_coverage", len(source_documents), detail_document_count)

    for name, source in manifest["sources"].items():
        path = ROOT / source["path"]
        audit.true(f"source_exists_{name}", path.exists(), source["path"])
        audit.check(f"source_hash_{name}", source["sha256"], sha256(path))

    report = {
        "ok": True,
        "datasetVersion": manifest["datasetVersion"],
        "checksPassed": len(audit.checks),
        "checks": audit.checks,
        "semantics": {
            "contractValue": "controlling confirmed awards only; not money paid",
            "defaultScope": "confirmed_gurugram only",
            "completion": "scheduled and actual completion remain separate",
        },
    }
    destination = DATA / "validation.json"
    with destination.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"ok": True, "checks": len(audit.checks), "report": str(destination)}))


if __name__ == "__main__":
    main()
