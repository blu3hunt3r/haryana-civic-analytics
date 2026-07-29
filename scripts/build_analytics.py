#!/usr/bin/env python3
"""Build public, versioned analytics artifacts from the verified local archive.

This script never edits the archive. It deliberately emits:
  * compact cross-filter rows, not the source CSVs;
  * precomputed overview dimensions for an instant first render;
  * 64 tender-detail shards containing document metadata and evidence hashes;
  * only contract values from confirmed controlling awards;
  * explicit scope, component and geography confidence.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import zlib
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REPO = Path(__file__).resolve().parents[1]
ROOT = Path(
    os.environ.get("CIVIC_DATA_ROOT", REPO.parent / "civic-stuff")
).resolve()
OUT = REPO / "public" / "data"
DETAIL_SHARDS = 64
INDEX_FIELDS = [
    "id",
    "title",
    "scope",
    "status",
    "awardState",
    "isAwarded",
    "isControllingAward",
    "estimateValue",
    "contractValue",
    "year",
    "month",
    "publishedDateConflict",
    "department",
    "component",
    "contractor",
    "contractorKey",
    "awardedBidCount",
    "chainRoot",
    "chainLength",
    "chainAmbiguous",
    "chainHasCancelOrRetender",
    "titleKey",
    "areas",
    "documentCount",
    "downloadedDocumentCount",
    "detailShard",
]

SOURCES = {
    "tenders": "data/final/tenders.csv",
    "scope": "data/final/gurugram_scope.csv",
    "documents": "data/final/documents.csv",
    "provenance": "data/final/field_provenance.csv",
    "awards": "data/derived/award_verification_v2.csv",
    "chains": "data/derived/procurement_chains.csv",
    "areas": "data/derived/tender_area_index.csv",
    "hewp": "data/hewp_gurugram_public_works_deduplicated.csv",
    "mcg": "data/mcg_public_execution_works.csv",
}

GEO_SOURCES = {
    "gurugram_boundary": "archive/features/gmda_boundary.geojson",
    "mcg_wards": "archive/features/wards_mcg.geojson",
    "gurugram_sectors": "archive/features/sectors.geojson",
    "mapped_roads": "data/layers/roads.geojson",
}

CONTEXT_GEO_SOURCES = {
    "haryana_districts": {
        "path": "data-sources/haryana-districts.geojson",
        "sourceUrl": (
            "https://mapservice.gov.in/gismapservice/rest/services/"
            "BharatMapService/Admin_Boundary_District/MapServer/1"
        ),
        "sourceAuthority": "BharatMaps / Government of India",
        "sourceNote": (
            "Administrative boundary service updated through the service's "
            "published year_stat fields; used as map context, not procurement evidence."
        ),
    }
}

SCOPES = (
    "confirmed_gurugram",
    "likely_gurugram",
    "statewide_multi_location",
    "not_gurugram",
)

COMPONENTS = [
    (
        "surface",
        r"resurfac|strengthen|pothole|pot hole|patch|widen|carriageway|"
        r"premix|bitumin|special repair|recarpet|\bBT\b",
    ),
    ("structure", r"flyover|bridge|subway|underpass|\bROB\b"),
    ("drainage", r"storm water|stormwater|nala|nallah|culvert|catch pit|drain"),
    ("sewer", r"sewerage|sewage|manhole|rising main|\bSTP\b"),
    ("water", r"water supply|tubewell|tube well|trunk main|water works"),
    ("lighting", r"street light|high mast|feeder pillar|\bLED\b"),
    ("footpath", r"footpath|paver|kerb|cycle track"),
    ("landscape", r"horticultur|plantation|green belt|beautif|landscap|\bpark\b"),
    ("fencing", r"fenc|chainlink|chain link|grill|boundary wall|railing"),
    ("consultancy", r"third party|consultan|survey|design|\bDPR\b|\bPMC\b"),
    ("sanitation", r"solid waste|garbage|sanitation|sweeping|housekeeping"),
    ("electricity", r"substation|sub-station|transformer|feeder|electrical"),
    ("building", r"building|office|hospital|school|college|quarters|stadium"),
]
COMPONENT_RX = [(name, re.compile(pattern, re.I)) for name, pattern in COMPONENTS]

DEPARTMENT_RULES = [
    ("Municipal Corporation / Urban Local Bodies", r"municipal|urban local bod|mcg"),
    ("GMDA", r"gurugram metropolitan|gmda"),
    ("HSVP / HUDA", r"shehri vikas|huda|hsvp"),
    ("HSIIDC", r"hsiidc|state industrial"),
    ("PWD (B&R)", r"public works|pwd|roads and bridges|pw\s*\(b\s*(and|&)\s*r\)"),
    ("Development & Panchayats", r"development and panchayat|panchayati raj"),
    ("PHED", r"public health engineering|phed"),
    ("DHBVN", r"dakshin haryana bijli|dhbvn"),
    ("HVPNL", r"vidyut prasaran|hvpn"),
    ("Irrigation & Water Resources", r"irrigation|water resources"),
    ("Police Housing", r"police housing"),
    ("School Education", r"school shiksha|school education|secondary education"),
    ("HSAMB", r"agriculture marketing board|hsamb"),
    ("Forest", r"\bforest|\bpccf\b"),
    ("University / Higher Education", r"university|higher education|college"),
    ("Housing Board", r"housing board"),
    ("Tourism", r"tourism"),
]
DEPARTMENT_RX = [(name, re.compile(pattern, re.I)) for name, pattern in DEPARTMENT_RULES]


def read_csv(relative: str) -> list[dict[str, str]]:
    path = ROOT / relative
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")


def number(value: str | None) -> float | None:
    try:
        if value is None or not value.strip():
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def integer(value: str | None) -> int | None:
    parsed = number(value)
    return int(parsed) if parsed is not None else None


def parse_tender_period(
    tender_id: str, published_at: str
) -> tuple[str | None, str | None, str, bool]:
    """Return stable tender year, optional month, basis and portal-date conflict.

    A large historical subset currently exposes 2026 in the portal's
    `published_at` field even though the government Tender ID starts with an
    earlier year. The ID year is stable and auditable; a month is only emitted
    when the two years agree.
    """
    id_match = re.match(r"^(20\d{2})_", tender_id or "")
    date_match = re.search(r"\b(20\d{2})\b", published_at or "")
    id_year = id_match.group(1) if id_match else None
    portal_year = date_match.group(1) if date_match else None
    year = id_year or portal_year
    if not year:
        return None, None, "missing", False
    conflict = bool(id_year and portal_year and id_year != portal_year)
    if conflict:
        return year, None, "tender_id_prefix_portal_date_conflict", True

    month_match = re.search(
        r"\b(\d{1,2})[-/](\d{1,2})[-/](20\d{2})\b", published_at or ""
    )
    if month_match:
        return year, f"{year}-{int(month_match.group(2)):02d}", (
            "tender_id_prefix_and_portal_date"
        ), False
    name_match = re.search(
        r"\b(\d{1,2})-([A-Za-z]{3})-(20\d{2})\b", published_at or ""
    )
    if name_match:
        months = {
            name: index
            for index, name in enumerate(
                "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1
            )
        }
        month = months.get(name_match.group(2).title())
        return year, f"{year}-{month:02d}" if month else None, (
            "tender_id_prefix_and_portal_date"
        ), False
    return year, None, "tender_id_prefix", False


def canonical_department(row: dict[str, str]) -> tuple[str, str]:
    haystack = " | ".join(
        value
        for value in (
            row.get("hewp_department", ""),
            row.get("organisation_chain", ""),
        )
        if value
    )
    for canonical, pattern in DEPARTMENT_RX:
        if pattern.search(haystack):
            return canonical, "explicit_name_rule"
    parts = [
        part.strip()
        for part in row.get("organisation_chain", "").split("||")
        if part.strip()
    ]
    meaningful = [
        part
        for part in parts
        if part.lower() not in {"haryana government", "haryana board corporation"}
    ]
    return (meaningful[0] if meaningful else (parts[0] if parts else "Unclassified")), (
        "organisation_chain"
    )


def classify_components(row: dict[str, str]) -> tuple[str, list[str], str]:
    description = row.get("work_description", "")
    description_hits = [name for name, rx in COMPONENT_RX if rx.search(description)]
    if description_hits:
        return description_hits[0], description_hits, "full_work_description_rule"

    title = row.get("title", "")
    title_hits = [name for name, rx in COMPONENT_RX if rx.search(title)]
    if title_hits:
        return title_hits[0], title_hits, "title_rule_lower_confidence"

    category = row.get("tender_category", "").lower()
    if category == "goods":
        return "goods", ["goods"], "portal_tender_category"
    if category == "services":
        return "services", ["services"], "portal_tender_category"
    return "unclassified", [], "no_rule_match"


def normalize_contractor(value: str) -> tuple[str, str]:
    if not value.strip():
        return "", ""
    normalized = value.upper().replace("&", " AND ")
    normalized = re.sub(r"[^A-Z0-9]+", " ", normalized)
    normalized = re.sub(
        r"\b(PRIVATE LIMITED|PVT LTD|PVT LIMITED|PRIVATE LTD)\b", " PVT LTD ", normalized
    )
    normalized = re.sub(r"\bLIMITED\b", " LTD ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    key = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return normalized, key


DISTRICT_ALIASES = {
    "Gurugram": ("gurugram", "gurgaon"),
    "Nuh": ("nuh", "mewat"),
    "Yamunanagar": ("yamunanagar", "yamuna nagar"),
    "Charkhi Dadri": ("charkhi dadri",),
    "Mahendragarh": ("mahendragarh", "mahendergarh"),
    "Sonipat": ("sonipat", "sonepat"),
}


def district_catalogue() -> list[str]:
    source = REPO / CONTEXT_GEO_SOURCES["haryana_districts"]["path"]
    if not source.exists():
        return []
    with source.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return sorted(
        {
            feature["properties"]["dtname"].strip()
            for feature in data.get("features", [])
            if feature.get("properties", {}).get("dtname")
        }
    )


def district_refs(row: dict[str, str], districts: list[str]) -> list[dict[str, str]]:
    fields = [
        ("work_location", row.get("work_location", ""), "high"),
        ("work_description", row.get("work_description", ""), "medium"),
        ("organisation_chain", row.get("organisation_chain", ""), "low"),
    ]
    found: dict[str, dict[str, str]] = {}
    for district in districts:
        aliases = DISTRICT_ALIASES.get(district, (district.lower(),))
        pattern = re.compile(
            r"(?<![a-z])(?:" + "|".join(re.escape(alias) for alias in aliases) + r")(?![a-z])",
            re.I,
        )
        for source_field, value, confidence in fields:
            if pattern.search(value or ""):
                found[district] = {
                    "level": "district",
                    "value": district,
                    "confidence": confidence,
                    "sourceField": source_field,
                }
                break
    return list(found.values())


def controlling_award(
    tender_id: str,
    award_state: str,
    chain: dict[str, str] | None,
) -> bool:
    if award_state != "AWARD_CONFIRMED":
        return False
    if not chain:
        return True
    if chain.get("chain_is_ambiguous") == "true":
        return False
    terminal = chain.get("terminal_tender_id", "")
    return not terminal or terminal == tender_id


def add_metric(bucket: dict[str, Any], row: dict[str, Any]) -> None:
    bucket["tenders"] += 1
    if row["isAwarded"]:
        bucket["awarded"] += 1
    if row["isControllingAward"] and row["contractValue"] is not None:
        bucket["contractValue"] += row["contractValue"]
    if row["status"] == "Cancelled":
        bucket["cancelled"] += 1
    if row["status"] == "Retender":
        bucket["retendered"] += 1


def metric_bucket() -> dict[str, Any]:
    return {
        "tenders": 0,
        "awarded": 0,
        "contractValue": 0.0,
        "cancelled": 0,
        "retendered": 0,
    }


def main() -> None:
    if not ROOT.exists():
        raise SystemExit(f"archive root does not exist: {ROOT}")

    resolved_out = OUT.resolve()
    if REPO.resolve() not in resolved_out.parents:
        raise SystemExit(f"unsafe output path: {resolved_out}")
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    tenders = read_csv(SOURCES["tenders"])
    scopes = {row["tender_id"]: row for row in read_csv(SOURCES["scope"])}
    awards = {row["tender_id"]: row for row in read_csv(SOURCES["awards"])}
    chains = {row["tender_id"]: row for row in read_csv(SOURCES["chains"])}
    area_rows = read_csv(SOURCES["areas"])
    documents = read_csv(SOURCES["documents"])
    districts = district_catalogue()

    areas_by_tender: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in area_rows:
        areas_by_tender[row["tender_id"]].append(
            {
                "level": row["area_level"],
                "value": row["area_value"],
                "confidence": row["confidence"],
                "sourceField": row["source_field"],
            }
        )

    document_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    document_summary: dict[str, Counter[str]] = defaultdict(Counter)
    for row in documents:
        tid = row["tender_id"]
        outcome = row["attempt_outcome"] or "unknown"
        document_summary[tid]["records"] += 1
        document_summary[tid][outcome] += 1
        if row.get("sha256"):
            document_summary[tid]["hashed"] += 1
        document_rows[tid].append(
            {
                "name": row["document_name"],
                "section": row["stage_or_section"],
                "outcome": outcome,
                "contentType": row["content_type"],
                "bytes": integer(row["bytes"]),
                "sha256": row["sha256"],
                "textStatus": row["text_extraction_status"],
                "officialUrl": row["document_url"],
            }
        )

    scope_metrics: dict[str, dict[str, Any]] = {
        scope: metric_bucket() for scope in SCOPES
    }
    status_metrics: dict[str, Counter[str]] = defaultdict(Counter)
    component_metrics: dict[str, dict[str, dict[str, Any]]] = defaultdict(
        lambda: defaultdict(metric_bucket)
    )
    department_metrics: dict[str, dict[str, dict[str, Any]]] = defaultdict(
        lambda: defaultdict(metric_bucket)
    )
    trend_metrics: dict[str, dict[str, dict[str, Any]]] = defaultdict(
        lambda: defaultdict(metric_bucket)
    )
    area_metrics: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(metric_bucket)
    contractor_metrics: dict[str, dict[str, Any]] = {}
    cross_filter_rows: list[dict[str, Any]] = []
    detail_shards: list[dict[str, Any]] = [dict() for _ in range(DETAIL_SHARDS)]

    for source in tenders:
        tid = source["tender_id"]
        scope = scopes.get(tid, {}).get("scope_classification", "unclassified")
        award = awards.get(tid, {})
        chain = chains.get(tid)
        award_state = award.get("award_state") or (
            "AWARD_CONFIRMED" if source["current_status"] == "AOC" else ""
        )
        contract_value = number(
            award.get("aoc_total_contract_value_inr")
            or source.get("aoc_total_contract_value_inr")
        )
        estimate_value = number(source.get("tender_value_inr"))
        is_awarded = award_state == "AWARD_CONFIRMED"
        is_controlling = controlling_award(tid, award_state, chain)
        component, components, component_basis = classify_components(source)
        department, department_basis = canonical_department(source)
        contractor = award.get("winning_contractor") or source.get("winning_contractor", "")
        contractor_normalized, contractor_key = normalize_contractor(contractor)
        year, month, year_basis, published_date_conflict = parse_tender_period(
            tid, source.get("published_at", "")
        )
        areas = [
            *areas_by_tender.get(tid, []),
            *district_refs(source, districts),
        ]
        doc_counts = document_summary.get(tid, Counter())
        shard = zlib.crc32(tid.encode("utf-8")) % DETAIL_SHARDS

        public_row = {
            "id": tid,
            "title": source["title"],
            "description": source["work_description"],
            "scope": scope,
            "status": source["current_status"],
            "awardState": award_state or "NOT_AWARDED",
            "isAwarded": is_awarded,
            "isControllingAward": is_controlling,
            "estimateValue": estimate_value,
            "contractValue": contract_value,
            "year": year,
            "month": month,
            "yearBasis": year_basis,
            "publishedDateConflict": published_date_conflict,
            "department": department,
            "departmentBasis": department_basis,
            "component": component,
            "components": components,
            "componentBasis": component_basis,
            "contractor": contractor,
            "contractorKey": contractor_key,
            "awardedBidCount": integer(
                award.get("awarded_bid_count") or source["awarded_bid_count"]
            ),
            "chainRoot": chain["chain_root"] if chain else tid,
            "chainLength": integer(chain["chain_length"]) if chain else 1,
            "chainAmbiguous": (
                chain["chain_is_ambiguous"] == "true" if chain else False
            ),
            "chainHasCancelOrRetender": (
                chain["chain_has_cancel_or_retender"] == "true" if chain else False
            ),
            "titleKey": chain["normalised_title"] if chain else "",
            "areas": areas,
            "documentCount": doc_counts.get("records", 0),
            "downloadedDocumentCount": doc_counts.get("downloaded", 0),
            "detailShard": shard,
        }
        cross_filter_rows.append(public_row)

        if scope in scope_metrics:
            add_metric(scope_metrics[scope], public_row)
        status_metrics[scope][public_row["status"]] += 1
        add_metric(component_metrics[scope][component], public_row)
        add_metric(department_metrics[scope][department], public_row)
        if month:
            add_metric(trend_metrics[scope][month], public_row)
        elif year:
            add_metric(trend_metrics[scope][year], public_row)
        district_count = sum(area["level"] == "district" for area in areas)
        for area in areas:
            area_metric_row = public_row
            if area["level"] == "district" and district_count != 1:
                # A multi-district contract is visible in each district's count,
                # but its full value cannot be assigned to each district.
                area_metric_row = {**public_row, "isControllingAward": False}
            add_metric(
                area_metrics[(scope, area["level"], area["value"])],
                area_metric_row,
            )

        if is_controlling and contract_value is not None and contractor_key:
            entry = contractor_metrics.setdefault(
                contractor_key,
                {
                    "key": contractor_key,
                    "name": contractor,
                    "normalizedName": contractor_normalized,
                    "awards": 0,
                    "contractValue": 0.0,
                    "departments": Counter(),
                    "components": Counter(),
                    "scopes": Counter(),
                    "normalizationConfidence": "name_only",
                },
            )
            entry["awards"] += 1
            entry["contractValue"] += contract_value
            entry["departments"][department] += 1
            entry["components"][component] += 1
            entry["scopes"][scope] += 1

        detail_shards[shard][tid] = {
            **public_row,
            "referenceNumber": source["tender_reference_number"],
            "organisationChain": source["organisation_chain"],
            "tenderCategory": source["tender_category"],
            "productCategory": source["product_category"],
            "contractType": source["contract_type"],
            "formOfContract": source["form_of_contract"],
            "workLocation": source["work_location"],
            "pincode": source["pincode"],
            "publishedAt": source["published_at"],
            "bidSubmissionEndAt": source["bid_submission_end_at"],
            "bidOpeningAt": source["bid_opening_at"],
            "awardDate": award.get("aoc_contract_date") or source["aoc_contract_date"],
            "scheduledCompletionDays": integer(source["aoc_completion_days"]),
            "contractorNormalized": contractor_normalized,
            "contractorState": award.get("contractor_state")
            or ("published" if contractor else "not_published"),
            "officialValueState": award.get("official_value_state", ""),
            "sourceHashes": {
                "status": source["status_sha256"],
                "summary": source["summary_sha256"],
                "detail": source["detail_sha256"],
                "frontTender": source["front_tender_sha256"],
                "awardSummary": award.get("source_summary_sha256", ""),
            },
            "officialStatusUrl": source["status_url"],
            "officialDetailUrl": source["detail_url"],
            "chain": (
                {
                    "root": chain["chain_root"],
                    "position": integer(chain["chain_position"]),
                    "successor": chain["successor_tender_id"],
                    "terminal": chain["terminal_tender_id"],
                    "length": integer(chain["chain_length"]),
                    "ambiguous": chain["chain_is_ambiguous"] == "true",
                    "hasCancelOrRetender": chain["chain_has_cancel_or_retender"] == "true",
                    "ambiguityReasons": chain["chain_ambiguity_reasons"],
                }
                if chain
                else None
            ),
            "documents": document_rows.get(tid, []),
            "evidenceLanguage": {
                "contractValue": "Published contract value; not money paid.",
                "scheduledCompletion": (
                    "Published schedule; not evidence of actual completion."
                ),
                "scope": "Geography classification carries its own confidence.",
            },
        }

    default_scopes = {"confirmed_gurugram"}
    default_rows = [row for row in cross_filter_rows if row["scope"] in default_scopes]
    expanded_rows = [
        row
        for row in cross_filter_rows
        if row["scope"] in {"confirmed_gurugram", "likely_gurugram"}
    ]
    default_award_value = sum(
        row["contractValue"] or 0
        for row in default_rows
        if row["isControllingAward"]
    )

    contractor_output = []
    for entry in contractor_metrics.values():
        contractor_output.append(
            {
                **{key: value for key, value in entry.items() if not isinstance(value, Counter)},
                "departments": dict(entry["departments"].most_common()),
                "components": dict(entry["components"].most_common()),
                "scopes": dict(entry["scopes"].most_common()),
            }
        )
    contractor_output.sort(
        key=lambda row: (-row["contractValue"], -row["awards"], row["normalizedName"])
    )

    def serialise_nested_metrics(
        metrics: dict[str, dict[str, dict[str, Any]]]
    ) -> dict[str, list[dict[str, Any]]]:
        return {
            scope: [
                {"key": key, **value}
                for key, value in sorted(
                    entries.items(),
                    key=lambda item: (-item[1]["tenders"], item[0]),
                )
            ]
            for scope, entries in metrics.items()
        }

    overview = {
        "datasetVersion": next(
            (
                row.get("dataset_version")
                for row in awards.values()
                if row.get("dataset_version")
            ),
            "local-archive",
        ),
        "definitions": {
            "publishedTender": "A tender record published by the procurement portal.",
            "awardedContract": "A record with verified AOC status.",
            "contractValue": "Published award/contract value; not money paid.",
            "scheduledCompletion": "Published contract schedule; not actual completion.",
            "actualCompletion": "Requires a completion certificate or equivalent evidence.",
        },
        "headline": {
            "publishedTendersAllScopes": len(cross_filter_rows),
            "confirmedGurugram": len(default_rows),
            "confirmedPlusLikelyGurugram": len(expanded_rows),
            "confirmedAwarded": sum(row["isAwarded"] for row in default_rows),
            "confirmedControllingContractValue": default_award_value,
        },
        "scopeMetrics": scope_metrics,
        "status": {scope: dict(counts.most_common()) for scope, counts in status_metrics.items()},
        "components": serialise_nested_metrics(component_metrics),
        "departments": serialise_nested_metrics(department_metrics),
        "trends": {
            scope: [
                {"period": period, **value}
                for period, value in sorted(entries.items())
            ]
            for scope, entries in trend_metrics.items()
        },
        "areas": [
            {"scope": scope, "level": level, "value": value, **metrics}
            for (scope, level, value), metrics in sorted(area_metrics.items())
        ],
        "contractors": contractor_output[:250],
        "reviewFlags": {
            "cancelledOrRetendered": sum(
                row["status"] in {"Cancelled", "Retender"} for row in default_rows
            ),
            "awardedWithoutDownloadedDocument": sum(
                row["isAwarded"] and row["downloadedDocumentCount"] == 0
                for row in default_rows
            ),
            "componentUnclassified": sum(
                row["component"] == "unclassified" for row in default_rows
            ),
            "areaEvidenceMissing": sum(not row["areas"] for row in default_rows),
            "portalPublishedDateConflictsWithTenderIdYear": sum(
                row["publishedDateConflict"] for row in default_rows
            ),
        },
    }

    write_json(OUT / "overview.json", overview)
    write_json(
        OUT / "tenders.json",
        {
            "schema": INDEX_FIELDS,
            "rows": [
                [row.get(field) for field in INDEX_FIELDS]
                for row in cross_filter_rows
            ],
        },
    )
    write_json(
        OUT / "search-index.json",
        [
            [row["id"], row["description"]]
            for row in cross_filter_rows
            if row["description"]
        ],
    )
    write_json(OUT / "contractors.json", contractor_output)
    for index, shard in enumerate(detail_shards):
        write_json(OUT / "tender-details" / f"{index:02d}.json", shard)

    geo_manifest = {}
    for name, relative in GEO_SOURCES.items():
        source = ROOT / relative
        if not source.exists():
            geo_manifest[name] = {"available": False, "sourcePath": relative}
            continue
        destination = OUT / "geo" / f"{name}.geojson"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        geo_manifest[name] = {
            "available": True,
            "sourcePath": relative,
            "sourceSha256": sha256(source),
            "publicPath": f"data/geo/{name}.geojson",
            "bytes": destination.stat().st_size,
        }

    for name, metadata in CONTEXT_GEO_SOURCES.items():
        source = REPO / metadata["path"]
        if not source.exists():
            geo_manifest[name] = {
                "available": False,
                "sourcePath": metadata["path"],
                "sourceUrl": metadata["sourceUrl"],
            }
            continue
        destination = OUT / "geo" / f"{name}.geojson"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        geo_manifest[name] = {
            "available": True,
            "sourcePath": metadata["path"],
            "sourceUrl": metadata["sourceUrl"],
            "sourceAuthority": metadata["sourceAuthority"],
            "sourceNote": metadata["sourceNote"],
            "sourceSha256": sha256(source),
            "publicPath": f"data/geo/{name}.geojson",
            "bytes": destination.stat().st_size,
        }

    source_manifest = {}
    for name, relative in SOURCES.items():
        path = ROOT / relative
        source_manifest[name] = {
            "path": relative,
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
        }

    generated_epoch = max(
        int((ROOT / relative).stat().st_mtime) for relative in SOURCES.values()
    )
    manifest = {
        "datasetVersion": overview["datasetVersion"],
        "generatedAt": datetime.fromtimestamp(
            generated_epoch, tz=timezone.utc
        ).isoformat(),
        "records": {
            "tenders": len(cross_filter_rows),
            "documents": len(documents),
            "areas": len(area_rows),
            "detailShards": DETAIL_SHARDS,
            "indexEncoding": "schema_and_rows",
        },
        "sources": source_manifest,
        "geometry": geo_manifest,
        "knownLimits": [
            "Haryana district geometry is contextual; tender-to-district links require an explicit district-name match.",
            "Contract value is not expenditure or money paid.",
            "Scheduled completion is not actual completion.",
            "Area text is not an exact asset link.",
            "Contractor normalization is name-based unless an authoritative identifier is published.",
        ],
    }
    write_json(OUT / "manifest.json", manifest)

    print(
        json.dumps(
            {
                "output": str(OUT),
                "tenders": len(cross_filter_rows),
                "documents": len(documents),
                "confirmed_gurugram": len(default_rows),
                "confirmed_plus_likely": len(expanded_rows),
                "detail_shards": DETAIL_SHARDS,
                "dataset_version": overview["datasetVersion"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
