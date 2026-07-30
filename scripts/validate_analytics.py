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
    tender_index = load_json(DATA / "tenders.json")
    tenders = [
        dict(zip(tender_index["schema"], row, strict=True))
        for row in tender_index["rows"]
    ]

    source_tenders = read_csv(ROOT / "data/final/tenders.csv")
    source_scope = read_csv(ROOT / "data/final/gurugram_scope.csv")
    source_documents = read_csv(ROOT / "data/final/documents.csv")
    source_hewp_links = read_csv(ROOT / "data/final/hewp_exact_links.csv")
    source_mcg_links = read_csv(ROOT / "data/final/mcg_gepnic_links.csv")
    source_asset_links = read_csv(ROOT / "data/derived/contract_asset_links.csv")
    source_places = read_csv(ROOT / "data/derived/gurugram_places.csv")
    places = load_json(DATA / "places.json")
    embedded_link_counts = Counter()
    for index in range(manifest["records"]["detailShards"]):
        shard = load_json(DATA / "tender-details" / f"{index:02d}.json")
        for detail in shard.values():
            embedded_link_counts["hewp"] += len(detail["hewpRecords"])
            embedded_link_counts["mcg"] += len(detail["mcgLinks"])
            embedded_link_counts["assets"] += len(detail["assetLinks"])

    source_ids = [row["tender_id"] for row in source_tenders]
    public_ids = [row["id"] for row in tenders]
    audit.check("source_tender_ids_unique", len(source_ids), len(set(source_ids)))
    audit.check("public_tender_ids_unique", len(public_ids), len(set(public_ids)))
    audit.check("public_tender_count", len(source_ids), len(public_ids))
    audit.check("public_tender_id_set", set(source_ids), set(public_ids))
    audit.check("place_count", len(source_places), len(places))
    audit.check(
        "place_index_contains_no_invented_boundaries",
        0,
        sum(place["boundaryGeometryAvailable"] for place in places),
    )
    audit.true(
        "place_tender_ids_resolve",
        {
            tender_id
            for place in places
            for tender_id in place["tenderIds"]
        }
        <= set(public_ids),
    )
    audit.check(
        "hewp_exact_link_count",
        len(source_hewp_links),
        manifest["records"]["hewpExactLinks"],
    )
    audit.check(
        "mcg_link_count",
        len(source_mcg_links),
        manifest["records"]["mcgLinks"],
    )
    audit.check(
        "confirmed_asset_link_count",
        sum(row["proof_grade"] == "B" for row in source_asset_links),
        manifest["records"]["confirmedAssetLinks"],
    )
    audit.check(
        "hewp_links_embedded_in_tender_details",
        len(source_hewp_links),
        embedded_link_counts["hewp"],
    )
    audit.check(
        "mcg_links_embedded_in_tender_details",
        len(source_mcg_links),
        embedded_link_counts["mcg"],
    )
    audit.check(
        "confirmed_asset_links_embedded_in_tender_details",
        sum(row["proof_grade"] == "B" for row in source_asset_links),
        embedded_link_counts["assets"],
    )

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

    story = load_json(DATA / "story.json")
    intelligence_manifest = load_json(DATA / "intelligence-manifest.json")
    audit.check(
        "story_full_corpus_count",
        len(tenders),
        story["all"]["records"],
    )
    audit.check(
        "story_confirmed_scope_count",
        len(confirmed),
        story["confirmedGurugram"]["records"],
    )
    audit.check(
        "story_confirmed_award_count",
        sum(row["isAwarded"] for row in confirmed),
        story["confirmedGurugram"]["awarded"],
    )
    audit.check(
        "story_confirmed_controlling_value",
        controlling_value,
        story["confirmedGurugram"]["contractValue"],
    )
    audit.check(
        "story_outcomes_partition_confirmed_scope",
        len(confirmed),
        sum(story["confirmedGurugram"]["outcomes"].values()),
    )
    completion_rows = [
        row
        for row in read_csv(ROOT / "data/derived/completion_evidence_scan.csv")
        if row["record_type"] == "confirmed_actual_completion_record"
    ]
    completion_tenders = {row["tender_id"] for row in completion_rows}
    audit.check(
        "reviewed_actual_completion_records",
        len(completion_tenders & {row["id"] for row in confirmed}),
        story["confirmedGurugram"]["evidence"]["actualCompletionEvidence"],
    )
    intelligence_ids: set[str] = set()
    intelligence_completion = 0
    for shard_path in sorted((DATA / "intelligence").glob("*.json")):
        shard = load_json(shard_path)
        audit.true(
            f"intelligence_shard_no_duplicate_{shard_path.stem}",
            intelligence_ids.isdisjoint(shard),
        )
        intelligence_ids.update(shard)
        intelligence_completion += sum(
            bool(row["actualCompletionEvidence"]) for row in shard.values()
        )
    audit.check(
        "intelligence_shard_count",
        intelligence_manifest["detailShards"],
        len(list((DATA / "intelligence").glob("*.json"))),
    )
    audit.check("intelligence_tender_coverage", set(public_ids), intelligence_ids)
    audit.check(
        "intelligence_completion_evidence_coverage",
        len(completion_tenders),
        intelligence_completion,
    )
    audit.check(
        "knowledge_graph_tender_count",
        len(tenders),
        intelligence_manifest["sourceRows"]["tenders"],
    )
    audit.true(
        "knowledge_graph_has_more_edges_than_tenders",
        intelligence_manifest["knowledgeGraph"]["edges"] > len(tenders),
    )

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
