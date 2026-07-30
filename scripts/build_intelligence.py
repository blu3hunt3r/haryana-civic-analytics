#!/usr/bin/env python3
"""Build the procurement relationship graph and narrative analytics.

The existing public index is the canonical, validated tender projection.  This
stage preserves the relationships that ordinary dashboards flatten away:
tender -> department, component, contractor, place, bidder, document, HEWP/MCG
work, asset and procurement-chain membership.

Outputs:
  * build/knowledge-graph.sqlite (local analytical store; not published)
  * public/data/story.json (small, precomputed narrative model)
  * public/data/intelligence/<shard>.json (on-demand tender intelligence)
  * public/data/relationship-summary.json (aggregate relationship edges)

All public claims remain evidence-bounded.  A contract value is never renamed
as expenditure, and a scheduled completion is never treated as actual work
completion.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sqlite3
import zlib
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


REPO = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CIVIC_DATA_ROOT", REPO.parent / "civic-stuff")).resolve()
PUBLIC = REPO / "public" / "data"
BUILD = REPO / "build"
SHARDS = 64


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")
    temporary.replace(path)


def read_csv(path: Path) -> Iterable[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        yield from csv.DictReader(handle)


def compact_text(value: str, limit: int = 360) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def number(value: Any) -> float | None:
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def stable_id(prefix: str, *values: str) -> str:
    digest = hashlib.sha256("\x1f".join(values).encode("utf-8")).hexdigest()[:20]
    return f"{prefix}:{digest}"


def shard_for(tender_id: str) -> int:
    return zlib.crc32(tender_id.encode("utf-8")) % SHARDS


def normalize_name(value: str) -> str:
    value = (value or "").upper().replace("&", " AND ")
    value = re.sub(r"[^A-Z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def outcome(row: dict[str, Any]) -> str:
    if row["isAwarded"]:
        return "awarded"
    if row["status"] == "Cancelled":
        return "cancelled"
    if row["status"] == "Retender":
        return "retendered"
    if row["status"] in {
        "Technical Bid Opening",
        "Technical Evaluation",
        "Financial Bid Opening",
        "Financial Evaluation",
    }:
        return "under_evaluation"
    return "other_published"


def evidence_level(
    row: dict[str, Any],
    award_document_downloaded: bool,
    has_hewp: bool,
    has_actual_completion: bool,
) -> str:
    if has_actual_completion:
        return "actual_completion_evidence"
    if has_hewp:
        return "exact_execution_register_link"
    if award_document_downloaded:
        return "award_document"
    if row["isAwarded"]:
        return "award_status_only"
    return "tender_notice"


def main() -> None:
    BUILD.mkdir(parents=True, exist_ok=True)
    index = load_json(PUBLIC / "tenders.json")
    tenders = [
        dict(zip(index["schema"], values, strict=True)) for values in index["rows"]
    ]
    by_id = {row["id"]: row for row in tenders}

    details: dict[str, dict[str, Any]] = {}
    for shard in range(SHARDS):
        details.update(
            load_json(PUBLIC / "tender-details" / f"{shard:02d}.json")
        )

    actual_completion: dict[str, list[dict[str, str]]] = defaultdict(list)
    completion_source = ROOT / "data/derived/completion_evidence_scan.csv"
    if completion_source.exists():
        for row in read_csv(completion_source):
            if row["record_type"] != "confirmed_actual_completion_record":
                continue
            actual_completion[row["tender_id"]].append(
                {
                    "date": row["actual_completion_date"],
                    "assessment": row["evidence_assessment"],
                    "context": compact_text(row["verbatim_context"], 520),
                    "page": row["page_number"],
                    "sha256": row["sha256"],
                    "sourcePath": row["source_path"],
                }
            )

    bids: dict[str, list[dict[str, Any]]] = defaultdict(list)
    bid_metrics: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "records": 0,
            "distinctBidders": set(),
            "accepted": 0,
            "rejected": 0,
            "notAdmitted": 0,
            "publishedFinancialValues": 0,
        }
    )
    bid_source = ROOT / "data/final/bid_history.csv"
    for row in read_csv(bid_source):
        tender_id = row["tender_id"]
        if tender_id not in by_id:
            continue
        bidder = row["bidder_name"].strip()
        status = row["bid_status"].strip()
        metric = bid_metrics[tender_id]
        metric["records"] += 1
        if bidder:
            metric["distinctBidders"].add(normalize_name(bidder))
        status_lower = status.lower()
        if "accepted" in status_lower or "admitted" in status_lower:
            metric["accepted"] += 1
        if "rejected" in status_lower:
            metric["rejected"] += 1
        if "not admitted" in status_lower:
            metric["notAdmitted"] += 1
        financial_value = number(row["financial_value_inr"])
        if financial_value is not None:
            metric["publishedFinancialValues"] += 1
        bids[tender_id].append(
            {
                "number": row["bid_number"],
                "bidder": bidder,
                "status": status,
                "submittedAt": row["submitted_at"],
                "rank": row["financial_rank"],
                "financialValue": financial_value,
                "isAwarded": row["is_awarded"].lower() == "true",
                "sourceSha256": row["source_summary_sha256"],
            }
        )

    lifecycle: dict[str, list[dict[str, str]]] = defaultdict(list)
    lifecycle_counts: dict[str, Counter[str]] = defaultdict(Counter)
    lifecycle_source = ROOT / "data/final/tender_lifecycle_events.csv"
    for row in read_csv(lifecycle_source):
        tender_id = row["tender_id"]
        if tender_id not in by_id:
            continue
        lifecycle_counts[tender_id][row["event_type"]] += 1
        lifecycle[tender_id].append(
            {
                "sequence": row["event_sequence"],
                "at": row["event_at"],
                "type": row["event_type"],
                "status": row["event_status"],
                "detail": compact_text(row["event_detail"], 260),
                "sourceType": row["source_page_type"],
                "sourceSha256": row["source_sha256"],
            }
        )

    flags: dict[str, list[dict[str, str]]] = defaultdict(list)
    flag_source = ROOT / "data/final/procurement_flags.csv"
    for row in read_csv(flag_source):
        tender_id = row["tender_id"]
        if tender_id not in by_id:
            continue
        flags[tender_id].append(
            {
                "id": row["flag_id"],
                "severity": row["severity"],
                "message": row["message"],
                "observedValue": row["observed_value"],
                "requiredEvidence": row["required_evidence"],
                "ruleSourceUrl": row["rule_source_url"],
                "notAnAccusation": row["not_an_accusation"].lower() == "true",
            }
        )

    intelligence_shards: list[dict[str, Any]] = [dict() for _ in range(SHARDS)]
    detail_evidence: dict[str, dict[str, Any]] = {}
    for tender_id, row in by_id.items():
        detail = details[tender_id]
        award_docs = [
            document
            for document in detail["documents"]
            if document["section"] in {"AOC", "Letter of Award"}
        ]
        award_document_downloaded = any(
            document["outcome"] == "downloaded" for document in award_docs
        )
        metric = bid_metrics.get(tender_id)
        compact_metric = {
            "records": metric["records"] if metric else 0,
            "distinctBidders": len(metric["distinctBidders"]) if metric else 0,
            "accepted": metric["accepted"] if metric else 0,
            "rejected": metric["rejected"] if metric else 0,
            "notAdmitted": metric["notAdmitted"] if metric else 0,
            "publishedFinancialValues": (
                metric["publishedFinancialValues"] if metric else 0
            ),
        }
        evidence = {
            "level": evidence_level(
                row,
                award_document_downloaded,
                bool(detail["hewpRecords"]),
                bool(actual_completion.get(tender_id)),
            ),
            "awardDocumentRecords": len(award_docs),
            "awardDocumentDownloaded": award_document_downloaded,
            "contractorPublished": bool(row["contractor"]),
            "contractValuePublished": row["contractValue"] is not None,
            "exactHewpLinks": len(detail["hewpRecords"]),
            "mcgLinks": len(detail["mcgLinks"]),
            "confirmedAssetLinks": len(detail["assetLinks"]),
            "actualCompletionRecords": len(actual_completion.get(tender_id, [])),
        }
        detail_evidence[tender_id] = evidence
        intelligence_shards[shard_for(tender_id)][tender_id] = {
            "understanding": {
                "outcome": outcome(row),
                "department": row["department"],
                "components": row.get("components") or [row["component"]],
                "scope": row["scope"],
                "places": row["areas"],
                "chainRoot": row["chainRoot"],
                "evidence": evidence,
                "bidMetrics": compact_metric,
                "lifecycleEventCounts": dict(lifecycle_counts.get(tender_id, {})),
            },
            "bids": bids.get(tender_id, []),
            "lifecycle": lifecycle.get(tender_id, []),
            "reviewFlags": flags.get(tender_id, []),
            "actualCompletionEvidence": actual_completion.get(tender_id, []),
        }

    for shard, rows in enumerate(intelligence_shards):
        write_json_atomic(PUBLIC / "intelligence" / f"{shard:02d}.json", rows)

    confirmed = [
        row for row in tenders if row["scope"] == "confirmed_gurugram"
    ]
    expanded = [
        row
        for row in tenders
        if row["scope"] in {"confirmed_gurugram", "likely_gurugram"}
    ]

    def scope_story(rows: list[dict[str, Any]]) -> dict[str, Any]:
        outcomes = Counter(outcome(row) for row in rows)
        awarded = [row for row in rows if row["isAwarded"]]
        controlling = [row for row in rows if row["isControllingAward"]]
        total_value = sum(row["contractValue"] or 0 for row in controlling)
        known_contractor = [row for row in controlling if row["contractor"]]
        known_value = sum(row["contractValue"] or 0 for row in known_contractor)
        contractor_values: Counter[str] = Counter()
        contractor_counts: Counter[str] = Counter()
        for row in known_contractor:
            contractor_values[row["contractorKey"]] += row["contractValue"] or 0
            contractor_counts[row["contractorKey"]] += 1
        contractor_names = {
            row["contractorKey"]: row["contractor"] for row in known_contractor
        }
        ranked_contractors = sorted(
            contractor_values,
            key=lambda key: (-contractor_values[key], contractor_names[key]),
        )

        department_component: dict[tuple[str, str], dict[str, float]] = defaultdict(
            lambda: {"tenders": 0, "awards": 0, "contractValue": 0}
        )
        for row in rows:
            key = (row["department"], row["component"])
            department_component[key]["tenders"] += 1
            if row["isAwarded"]:
                department_component[key]["awards"] += 1
            if row["isControllingAward"]:
                department_component[key]["contractValue"] += row["contractValue"] or 0

        repeat_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            if row["titleKey"]:
                repeat_groups[row["titleKey"]].append(row)
        repeats = []
        for key, group in repeat_groups.items():
            years = sorted({row["year"] for row in group if row["year"]})
            if len(group) < 2 or len(years) < 2:
                continue
            repeats.append(
                {
                    "key": key,
                    "title": max(group, key=lambda row: len(row["title"]))["title"],
                    "records": len(group),
                    "awarded": sum(row["isAwarded"] for row in group),
                    "contractValue": sum(
                        row["contractValue"] or 0
                        for row in group
                        if row["isControllingAward"]
                    ),
                    "years": years,
                    "departments": sorted({row["department"] for row in group}),
                    "components": sorted({row["component"] for row in group}),
                    "tenderIds": [row["id"] for row in group],
                }
            )
        repeats.sort(
            key=lambda entry: (
                -entry["records"],
                -len(entry["years"]),
                -entry["contractValue"],
                entry["title"],
            )
        )

        competition = Counter()
        for row in awarded:
            count = row["awardedBidCount"]
            if count is None:
                competition["not_published"] += 1
            elif count == 1:
                competition["one_awarded_bid"] += 1
            elif count <= 3:
                competition["two_to_three_awarded_bids"] += 1
            else:
                competition["four_plus_awarded_bids"] += 1

        award_delta = Counter()
        delta_records = []
        for row in controlling:
            estimate = row["estimateValue"]
            contract = row["contractValue"]
            if not estimate or contract is None:
                award_delta["not_comparable"] += 1
                continue
            percent = (contract - estimate) / estimate * 100
            if percent < -10:
                bucket = "more_than_10_below_estimate"
            elif percent < -1:
                bucket = "one_to_10_below_estimate"
            elif percent <= 1:
                bucket = "within_one_percent"
            elif percent <= 10:
                bucket = "one_to_10_above_estimate"
            else:
                bucket = "more_than_10_above_estimate"
            award_delta[bucket] += 1
            delta_records.append((abs(percent), percent, row["id"]))
        delta_records.sort(reverse=True)

        evidence = {
            "awarded": len(awarded),
            "contractValuePublished": sum(
                detail_evidence[row["id"]]["contractValuePublished"] for row in awarded
            ),
            "contractorPublished": sum(
                detail_evidence[row["id"]]["contractorPublished"] for row in awarded
            ),
            "awardDocumentDownloaded": sum(
                detail_evidence[row["id"]]["awardDocumentDownloaded"] for row in awarded
            ),
            "exactHewpLink": sum(
                bool(detail_evidence[row["id"]]["exactHewpLinks"]) for row in awarded
            ),
            "actualCompletionEvidence": sum(
                bool(detail_evidence[row["id"]]["actualCompletionRecords"])
                for row in awarded
            ),
        }

        concentration = []
        cumulative = 0.0
        for rank, key in enumerate(ranked_contractors[:40], 1):
            value = contractor_values[key]
            cumulative += value
            concentration.append(
                {
                    "rank": rank,
                    "key": key,
                    "name": contractor_names[key],
                    "awards": contractor_counts[key],
                    "contractValue": value,
                    "shareOfAllPublishedValue": value / total_value if total_value else 0,
                    "shareOfKnownContractorValue": value / known_value if known_value else 0,
                    "cumulativeKnownValueShare": (
                        cumulative / known_value if known_value else 0
                    ),
                }
            )

        return {
            "records": len(rows),
            "outcomes": dict(outcomes),
            "awarded": len(awarded),
            "controllingAwards": len(controlling),
            "contractValue": total_value,
            "evidence": evidence,
            "competition": dict(competition),
            "awardVsEstimate": dict(award_delta),
            "largestAwardEstimateDifferences": [
                {"tenderId": tender_id, "differencePercent": percent}
                for _, percent, tender_id in delta_records[:25]
            ],
            "contractorCoverage": {
                "publishedContractorAwards": len(known_contractor),
                "publishedContractorValue": known_value,
                "unattributedContractValue": total_value - known_value,
            },
            "contractorConcentration": concentration,
            "departmentComponentEdges": [
                {
                    "department": department,
                    "component": component,
                    **metrics,
                }
                for (department, component), metrics in sorted(
                    department_component.items(),
                    key=lambda item: (
                        -item[1]["contractValue"],
                        -item[1]["tenders"],
                        item[0],
                    ),
                )
            ],
            "repeatGroups": repeats[:120],
            "relationshipCounts": {
                "department": len({row["department"] for row in rows}),
                "component": len({row["component"] for row in rows}),
                "contractor": len(
                    {row["contractorKey"] for row in rows if row["contractorKey"]}
                ),
                "placeReferences": sum(len(row["areas"]) for row in rows),
                "documents": sum(row["documentCount"] for row in rows),
                "bidRecords": sum(bid_metrics.get(row["id"], {}).get("records", 0) for row in rows),
                "lifecycleEvents": sum(
                    sum(lifecycle_counts.get(row["id"], {}).values()) for row in rows
                ),
            },
        }

    story = {
        "datasetVersion": load_json(PUBLIC / "overview.json")["datasetVersion"],
        "generatedFrom": {
            "tenders": "public/data/tenders.json",
            "details": "public/data/tender-details/*.json",
            "bids": "data/final/bid_history.csv",
            "lifecycle": "data/final/tender_lifecycle_events.csv",
            "flags": "data/final/procurement_flags.csv",
            "completionEvidence": "data/derived/completion_evidence_scan.csv",
        },
        "definitions": {
            "tender": "A published invitation to bid.",
            "award": "A tender with verified AOC status.",
            "contractValue": "Published contract value; not money paid.",
            "actualCompletion": "Only counted when a reviewed completion record names the tender's work.",
            "reviewSignal": "A reproducible pattern for inspection, not an allegation.",
        },
        "all": scope_story(tenders),
        "confirmedGurugram": scope_story(confirmed),
        "confirmedPlusLikely": scope_story(expanded),
    }
    write_json_atomic(PUBLIC / "story.json", story)

    relationship_summary = {
        "datasetVersion": story["datasetVersion"],
        "scopes": {
            "all": story["all"]["relationshipCounts"],
            "confirmedGurugram": story["confirmedGurugram"]["relationshipCounts"],
            "confirmedPlusLikely": story["confirmedPlusLikely"]["relationshipCounts"],
        },
        "edgeTypes": [
            "PUBLISHED_BY",
            "CLASSIFIED_AS",
            "LOCATED_IN",
            "AWARDED_TO",
            "HAS_DOCUMENT",
            "HAS_BID",
            "HAS_LIFECYCLE_EVENT",
            "MEMBER_OF_CHAIN",
            "LINKED_TO_HEWP",
            "LINKED_TO_MCG",
            "COVERS_ASSET",
        ],
        "note": "Counts describe published relationships. Candidate MCG links remain labelled candidates.",
    }
    write_json_atomic(PUBLIC / "relationship-summary.json", relationship_summary)

    database_tmp = BUILD / "knowledge-graph.sqlite.tmp"
    database = BUILD / "knowledge-graph.sqlite"
    if database_tmp.exists():
        database_tmp.unlink()
    connection = sqlite3.connect(database_tmp)
    connection.executescript(
        """
        PRAGMA journal_mode=OFF;
        PRAGMA synchronous=OFF;
        CREATE TABLE entity (
          entity_id TEXT PRIMARY KEY,
          entity_type TEXT NOT NULL,
          label TEXT NOT NULL,
          attributes_json TEXT NOT NULL,
          evidence_sha256 TEXT
        );
        CREATE TABLE edge (
          source_id TEXT NOT NULL,
          relation TEXT NOT NULL,
          target_id TEXT NOT NULL,
          attributes_json TEXT NOT NULL,
          evidence_sha256 TEXT,
          confidence TEXT NOT NULL,
          PRIMARY KEY (source_id, relation, target_id, evidence_sha256)
        );
        CREATE INDEX edge_source ON edge(source_id);
        CREATE INDEX edge_target ON edge(target_id);
        CREATE INDEX entity_type ON entity(entity_type);
        CREATE TABLE source_file (
          path TEXT PRIMARY KEY,
          bytes INTEGER NOT NULL,
          mtime_ns INTEGER NOT NULL
        );
        """
    )

    def add_entity(
        entity_id: str,
        entity_type: str,
        label: str,
        attributes: dict[str, Any],
        evidence_sha256: str = "",
    ) -> None:
        connection.execute(
            "INSERT OR IGNORE INTO entity VALUES (?,?,?,?,?)",
            (
                entity_id,
                entity_type,
                label,
                json.dumps(attributes, ensure_ascii=False, separators=(",", ":")),
                evidence_sha256,
            ),
        )

    def add_edge(
        source: str,
        relation: str,
        target: str,
        attributes: dict[str, Any],
        evidence_sha256: str = "",
        confidence: str = "published",
    ) -> None:
        connection.execute(
            "INSERT OR IGNORE INTO edge VALUES (?,?,?,?,?,?)",
            (
                source,
                relation,
                target,
                json.dumps(attributes, ensure_ascii=False, separators=(",", ":")),
                evidence_sha256,
                confidence,
            ),
        )

    for position, row in enumerate(tenders, 1):
        tender_id = f"tender:{row['id']}"
        detail = details[row["id"]]
        evidence_hash = detail["sourceHashes"].get("detail", "")
        add_entity(
            tender_id,
            "tender",
            row["title"],
            {
                "tenderId": row["id"],
                "scope": row["scope"],
                "status": row["status"],
                "year": row["year"],
                "estimateValue": row["estimateValue"],
                "contractValue": row["contractValue"],
                "outcome": outcome(row),
            },
            evidence_hash,
        )
        department_id = stable_id("department", row["department"])
        add_entity(department_id, "department", row["department"], {})
        add_edge(tender_id, "PUBLISHED_BY", department_id, {}, evidence_hash)
        for component in row.get("components") or [row["component"]]:
            component_id = f"component:{component}"
            add_entity(component_id, "component", component, {})
            add_edge(
                tender_id,
                "CLASSIFIED_AS",
                component_id,
                {"basis": row.get("componentBasis", "")},
                evidence_hash,
                "derived",
            )
        if row["contractorKey"]:
            contractor_id = f"contractor:{row['contractorKey']}"
            add_entity(
                contractor_id,
                "contractor",
                row["contractor"],
                {"normalization": "name_based"},
            )
            add_edge(
                tender_id,
                "AWARDED_TO",
                contractor_id,
                {"contractValue": row["contractValue"]},
                detail["sourceHashes"].get("summary", ""),
            )
        chain_id = f"chain:{row['chainRoot']}"
        add_entity(chain_id, "procurement_chain", row["chainRoot"], {})
        add_edge(
            tender_id,
            "MEMBER_OF_CHAIN",
            chain_id,
            {"length": row["chainLength"], "ambiguous": row["chainAmbiguous"]},
            "",
            "derived",
        )
        for area in row["areas"]:
            area_id = stable_id("area", area["level"], area["value"])
            add_entity(
                area_id,
                "area",
                area["value"],
                {"level": area["level"]},
            )
            add_edge(
                tender_id,
                "LOCATED_IN",
                area_id,
                {"sourceField": area["sourceField"]},
                evidence_hash,
                area["confidence"],
            )
        for document in detail["documents"]:
            document_id = (
                f"document:{document['sha256']}"
                if document["sha256"]
                else stable_id(
                    "document-record", row["id"], document["section"], document["name"]
                )
            )
            add_entity(
                document_id,
                "document",
                document["name"] or document["section"],
                {
                    "section": document["section"],
                    "outcome": document["outcome"],
                    "textStatus": document["textStatus"],
                },
                document["sha256"],
            )
            add_edge(
                tender_id,
                "HAS_DOCUMENT",
                document_id,
                {"section": document["section"], "outcome": document["outcome"]},
                document["sha256"],
            )
        for bid in bids.get(row["id"], []):
            bidder_name = bid["bidder"] or f"Withheld bidder {bid['number']}"
            bidder_id = stable_id("bidder", normalize_name(bidder_name))
            add_entity(
                bidder_id,
                "bidder",
                bidder_name,
                {"identity": "display_name_only"},
                bid["sourceSha256"],
            )
            add_edge(
                tender_id,
                "HAS_BID",
                bidder_id,
                {
                    "status": bid["status"],
                    "rank": bid["rank"],
                    "isAwarded": bid["isAwarded"],
                },
                bid["sourceSha256"],
            )
        for record in detail["hewpRecords"]:
            work_id = stable_id(
                "hewp", record["sourceSha256"], record["place"], record["estimateName"]
            )
            add_entity(
                work_id,
                "hewp_work",
                record["estimateName"] or record["place"],
                {"place": record["place"], "agreement": record["agreementName"]},
                record["sourceSha256"],
            )
            add_edge(
                tender_id,
                "LINKED_TO_HEWP",
                work_id,
                {"method": record["linkMethod"]},
                record["sourceSha256"],
                "exact_identifier",
            )
        for record in detail["mcgLinks"]:
            work_id = f"mcg:{record['workId']}"
            add_entity(
                work_id,
                "mcg_work",
                record["workName"],
                {"grade": record["linkGrade"], "method": record["linkMethod"]},
            )
            add_edge(
                tender_id,
                "LINKED_TO_MCG",
                work_id,
                {"interpretation": record["interpretation"]},
                "",
                record["linkGrade"],
            )
        for record in detail["assetLinks"]:
            asset_id = f"asset:{record['assetKey']}"
            add_entity(asset_id, "asset", record["assetKey"], {})
            add_edge(
                tender_id,
                "COVERS_ASSET",
                asset_id,
                {
                    "component": record["component"],
                    "coverage": record["coverage"],
                    "reason": record["validatorReason"],
                },
                record["evidenceSha256"],
                record["proofGrade"],
            )
        if position % 1000 == 0:
            connection.commit()

    for path in [
        PUBLIC / "tenders.json",
        bid_source,
        lifecycle_source,
        flag_source,
        completion_source,
    ]:
        if path.exists():
            stat = path.stat()
            connection.execute(
                "INSERT INTO source_file VALUES (?,?,?)",
                (str(path), stat.st_size, stat.st_mtime_ns),
            )
    connection.commit()
    entity_count = connection.execute("SELECT COUNT(*) FROM entity").fetchone()[0]
    edge_count = connection.execute("SELECT COUNT(*) FROM edge").fetchone()[0]
    connection.close()
    database_tmp.replace(database)

    write_json_atomic(
        PUBLIC / "intelligence-manifest.json",
        {
            "datasetVersion": story["datasetVersion"],
            "detailShards": SHARDS,
            "knowledgeGraph": {
                "entities": entity_count,
                "edges": edge_count,
                "localPath": "build/knowledge-graph.sqlite",
                "published": False,
            },
            "sourceRows": {
                "tenders": len(tenders),
                "bids": sum(len(rows) for rows in bids.values()),
                "lifecycleEvents": sum(len(rows) for rows in lifecycle.values()),
                "reviewFlags": sum(len(rows) for rows in flags.values()),
                "actualCompletionRecords": sum(
                    len(rows) for rows in actual_completion.values()
                ),
            },
        },
    )
    print(
        json.dumps(
            {
                "tenders": len(tenders),
                "entities": entity_count,
                "edges": edge_count,
                "intelligenceShards": SHARDS,
                "actualCompletionRecords": sum(
                    len(rows) for rows in actual_completion.values()
                ),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
