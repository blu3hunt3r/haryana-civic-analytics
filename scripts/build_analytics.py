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
# Build intermediates. tenders.json and the 64 detail shards feed build_intelligence.py
# and build_tender_packages.py; they are NOT published — the browsing index and the
# per-tender packages replaced them. Writing them into public/ made every rebuild stage
# them back into the deploy by accident, and forced a manual copy before packaging.
SHARDS_OUT = REPO / "build" / "shards"
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
    "contractModes",
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
    "hewp_exact_links": "data/final/hewp_exact_links.csv",
    "mcg": "data/mcg_public_execution_works.csv",
    "mcg_links": "data/final/mcg_gepnic_links.csv",
    "places": "data/derived/gurugram_places.csv",
    "contract_asset_links": "data/derived/contract_asset_links.csv",
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

# ── THE COMPONENT CLASSIFIER ─────────────────────────────────────────────────────
# Tuned against the real descriptions with scripts/tune_components.py, which reports the
# unclassified rate, what each rule catches, rule collisions, and the commonest still-
# unmatched terms as the worklist for the next pass. Re-run it after any edit here.
#
# Unclassified fell from 21,470 (43.7% of the corpus) to 7,804 (15.9%) over four passes.
# The rules encode Haryana public-works shorthand that no general vocabulary contains —
# IPB, WBM, GSB, DBM, AR of LR, rasta, FHTC, disty, T/F, RDS, MGJG — and every
# abbreviation carries a comment saying what it stands for, because none of them are
# guessable by a reader who has not seen an estimate.
#
# Two classes of bug found by tuning and worth not reintroducing:
#   * \bpark\b does not match "parks", and \btree\b does not match "Trees". Plurals cost
#     several hundred tenders each until they were spotted in the residue.
#   * \bFHTC\b never fires inside "Gadaipur784FHTC2nd" because a digit-letter boundary is
#     not a word boundary. Descriptions in this corpus are frequently run together.
#
# ORDER IS SIGNIFICANT: first match wins. `building` is last on purpose — "office",
# "school" and "hospital" appear as LOCATIONS in descriptions of road and drain work, so
# a building rule placed earlier steals them from the true component.
COMPONENTS = [
    # Roads and paving. IPB = interlocking paver block, WBM = water bound macadam,
    # BT = bitumen, GSB = granular sub-base, DBM = dense bituminous macadam,
    # AR of LR = annual repair of link roads, "rasta" = a village path,
    # S/R + Wdg./Stg. = special repair, widening and strengthening.
    ("surface",
     r"resurfac|strengthen|pot\s?hole|patch|widen|carriageway|premix|bitumin|"
     r"special\s+repair|re-?carpet|black\s?top|\bBT\b|\bWBM\b|water\s*bound\s*macadam|"
     r"\bIPB\b|inter\s*locking\s*paver|interlocking\s+(paver|tile)|\bGSB\b|\bDBM\b|"
     r"\bC\.?C\.?\s*(locking|road|street|pavement)|\bRMC\b|\bM-?\d{2}\b|"
     r"\bAR\s+OF\s+LR\b|annual\s+repair\s+of\s+(various\s+)?link|\bPAV\b|paving|"
     r"\brasta\b|\btopping\b|\bberm\b|\bS/?R\b.*\b(Wdg|Stg|raising)|\bmetalling\b|"
     r"link\s+road|\broad\s+from\b|\bAR\s+of\s+(various\s+)?LR\b|\bLR\s+Group|"
     r"\bBM\s+(and\s+)?BC\b"),
    # Distinct structures before generic building.
    ("structure",
     r"flyover|bridge|subway|underpass|\bROB\b|\bRUB\b|retaining\s+wall|"
     r"culvert\s+cross|\bcauseways?\b"),
    ("drainage",
     r"storm\s*water|\bnala\b|nallah|catch\s*pit|\bdrain|desilt|\bSWD\b|"
     r"\bRCC\s+drain|water\s+logging|waterlogg|de-?watering|"
     r"disposal\s+of\s+water"),
    ("sewer",
     r"sewer|sewage|manhole|rising\s+main|\bSTP\b|sullage|septic|\bMH\b\s*cover|"
     r"\beffluent\b|grey\s+water|waste\s*water|super\s+sucker|jetting\s+machine"),
    # FHTC = Functional Household Tap Connection (the Jal Jeevan Mission scheme name),
    # disty = distributary, johad/pond = a village water body, RWH = rainwater harvesting.
    ("water",
     r"water\s+supply|tube\s*well|trunk\s+main|water\s+works|\bOHSR\b|\bUGR\b|"
     r"hand\s*pump|\bboring\b|FHTC|potable|\bWTP\b|pipe\s*line|"
     r"\bpump(ing)?\b|\bdisty\b|distributary|\bjohads?\b|\bponds?\b|water\s+body|"
     r"water\s+tanker|\btankers?\b|\bRWH\b|rain\s*water\s+harvest|\bwaterworks\b|\bJJM\b|tap\s+connection|"
     r"water\s+line|\btanki\b|water\s+course"),
    ("lighting",
     r"street\s*light|high\s*mast|feeder\s+pillar|\bLED\b|decorative\s+light|"
     r"fancy\s+light|\bpoles?\b.*light|light\s+point"),
    ("footpath", r"footpath|\bkerb\b|cycle\s+track|\bpaver\s+block\b"),
    ("landscape",
     r"horticultur|plantation|plant(ing)?\b|green\s*belt|beautif|landscap|\bparks?\b|"
     r"\btrees?\b|\bfelling\b|\bstump|shrub|ornamental|nursery|forestry|\bgardens?\b|lawn|\bL/?S\s+work\b|"
     r"play\s+equipment|playground|open\s+(air\s+)?gym"),
    ("fencing",
     r"fenc|chain\s*link|\bgrill|boundary\s+wall|railing|barbed|\bgabion\b"),
    # NEW CATEGORY. Stray-dog sterilisation, cattle pounds, animal birth control.
    ("animal_control",
     r"stray\s+(dog|pig|animal|monkey)s?|steril[iy]|vaccinat|deworm|neuter|cattle|\bgaushala\b|"
     r"animal\s+birth|\bABC\b\s+programme|dog\s+catch|humane\s+catch"),
    # NEW CATEGORY. Air conditioning is procured constantly and is not "electricity".
    ("hvac",
     r"air\s*condition|\bHVAC\b|\bchiller\b|\bAHU\b|\bVRF\b|\bACs?\b\s+(installed|at|in)|"
     r"\bsplit\s+AC\b|cooling\s+system|water\s+heating"),
    # Computers, CCTV, servers and licences. Repeatedly procured and not "goods" in any
    # useful sense — the portal's own category is blank for most of these.
    ("it_equipment",
     r"\bhardware\b|\bsoftware\b|\bcomputer|\blaptop|\bprinter|\bserver\b|"
     r"\bCCTV\b|\bUPS\b|licenc?s?ing|\bLENOVO\b|\bnetworking\b|\bdata\s+cent|"
     r"commissioning\s+of\s+all\s+hardware|\bEPABX\b|audio\s+conference|"
     r"attendance\s+management|biometric|video\s+record"),
    # Land acquisition and right-of-way work: demarcation, valuation, joint measurement.
    ("land",
     r"land\s+acquisit|demarcat|\bROW\b|right\s+of\s+way|joint\s+measurement|"
     r"\bvaluation\b|\bmutation\b|\bkhasra\b|encroachment"),
    # Traffic management is not street lighting and not a road surface.
    ("traffic",
     r"traffic\s+(light|signal|management)|\bjunctions?\b|\bchowks?\b|road\s+marking|"
     r"\bsignage\b|\bblinkers?\b|parking\s+system|\bzebra\b|\bbollard"),
    # Advance stockpiling of aggregate/material for the coming year's road repair.
    ("goods", r"collection\s+of\s+material|supply\s+(and\s+stacking\s+)?of\s+material"),
    # Municipal revenue outsourcing: toll points, tehbazari (street-vendor ground rent).
    ("services", r"collection\s+of\s+toll|toll\s+collection|tehbazari|advertisement\s+rights"),
    ("consultancy",
     r"third\s+party|consultan|feasibility|\bDPR\b|\bPMC\b|survey\s+and\s+(design|invest)|"
     r"empanelment|"
     r"design\s+consult|\bQA/?QC\b"),
    ("sanitation",
     r"solid\s+waste|garbage|sanitation|sweeping|housekeeping|\bMSW\b|door.to.door|"
     r"\bC\s*&\s*D\s+waste|dead\s+animal|toilet|urinal|\bpublic\s+convenience\b"),
    # T/F = transformer, RDS = rural distribution system, LD = load development,
    # MGJG = Mhatma Gandhi Jan Gram Jyoti (a rural electrification scheme).
    ("electricity",
     r"sub-?\s?station|transformer|electrificat|\bLT\b|\bHT\b|\bKV\b|"
     r"wiring|electrical\s+(work|installation)|\bDG\s+sets?\b|\bpanels?\b|"
     r"\bT/F\b|\bfeeders?\b|\bRDS\b|\bMGJG\b|\bLD\s+system\b|\bXen\s+Op\b|"
     r"\bconductor\b|\bHVDS\b|\bmeter(ing)?\b|power\s+supply|\bLRP\b|"
     r"\bSCADA\b|\bRDSS\b|\bDMS/?OMS\b"),
    # Building last: "office", "school" and "hospital" appear as LOCATIONS in
    # descriptions of road and drain work, so a building rule placed earlier steals them.
    ("building",
     r"\bbuilding\b|\bchaupal\b|community\s+cent|dwelling|\bquarters?\b|\bhalls?\b|"
     r"\bsheds?\b|\bbooths?\b|barat\s*ghar|brick\s*work|\bplaster|\bCPLASTER\b|"
     r"renovat|flooring|\btiles?\b|\bhospital\b|\bschool\b|\bstadium\b|\boffice\b|"
     r"\bcollege\b|\bcrematori|shamshan|\bghat\b|\btoilet\s+block\b|fire\s+fighting|fire\s+hydrant|"
     r"\brooms?\b|\bcentre\b|\bcenter\b|\bcomplex\b|\bRCC\b|\bcabins?\b|\blibrary\b|"
     r"\bgymnasium\b|\banganwadi\b|\bPHC\b|\bCHC\b|\bdispensary\b|\bveranda|"
     r"\bNGM\b|\bNVM\b|(various|committee)\s+propert|\bkabristan\b|\bcemet|\bcanteens?\b|"
     r"distemper|snowcem|white\s*wash|pucca\s+platform"),
]

MODES = [
    ("maintenance",
     r"annual\s+(repair|maintenance)|\bAMC\b|\bCMC\b|comprehensive\s+maintenance|"
     r"\bA/?M\s+OF\b|\bA/?Mtc\b|\bmtc\.?\b|day\s*to\s*day\s+(repair|mainten)|"
     r"operation\s+(and|&)\s+mainten|\bO\s*&\s*M\b|upkeep|\bR/?M\s+of\b"),
    ("hired_capacity",
     r"\bhiring\b|\bhire\s+of\b|\bon\s+rent\b|\brental\b|"
     r"engagement\s+of\s+(manpower|labour|agency)|deployment\s+of\s+(manpower|vehicle)"),
    # 300+ descriptions carry "RECALL" in the text — the office marking a re-tender in
    # the title. It says nothing about the work and everything about the procurement.
    ("recalled", r"\bre-?call(ed)?\b|\bre-?invit|\bre-?tender"),
    # The original contractor defaulted and the remaining work is re-bought at the
    # defaulter's expense. 131 tenders carry the clause verbatim; it is the only
    # contractor-default signal anywhere in the structured data.
    ("risk_and_cost", r"risk\s+(and|&)\s+cost"),
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


def department_unit(row: dict[str, str]) -> str:
    """The LEAF body in the organisation chain — the office that actually ran the
    procurement. The canonical department above answers "which arm of government";
    this answers "which of its 189 offices", so MC Sohna stops answering for MC
    Gurgaon inside the Urban Local Bodies line. Returned verbatim (whitespace
    collapsed): the raw names are clean — 189 distinct leaves, one case duplicate —
    and inventing canonical spellings here would trade a checkable name for a
    guessed one."""
    parts = [
        " ".join(part.split())
        for part in row.get("organisation_chain", "").split("||")
        if part.strip()
    ]
    meaningful = [
        part
        for part in parts
        if part.lower() not in {"haryana government", "haryana board corporation"}
    ]
    return meaningful[-1] if meaningful else (parts[-1] if parts else "")


MODE_RX = [(name, re.compile(pattern, re.I)) for name, pattern in MODES]


def classify_modes(row: dict[str, str]) -> list[str]:
    """How the work was bought, which is orthogonal to what the work was.

    "Annual maintenance of parks" is landscape work under a maintenance contract. Making
    that a component forced the classifier to discard one true fact to record another —
    1,375 descriptions collided on landscape+maintenance alone. Modes are recorded
    alongside the component instead of competing with it.
    """
    haystack = f"{row.get('work_description', '')} {row.get('title', '')}"
    return [name for name, rx in MODE_RX if rx.search(haystack)]


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
    for stale in (SHARDS_OUT / "tenders.json", SHARDS_OUT / "tender-details"):
        if stale.is_dir():
            shutil.rmtree(stale)
        elif stale.exists():
            stale.unlink()
    (SHARDS_OUT / "tender-details").mkdir(parents=True)

    tenders = read_csv(SOURCES["tenders"])
    scopes = {row["tender_id"]: row for row in read_csv(SOURCES["scope"])}
    awards = {row["tender_id"]: row for row in read_csv(SOURCES["awards"])}
    chains = {row["tender_id"]: row for row in read_csv(SOURCES["chains"])}
    area_rows = read_csv(SOURCES["areas"])
    documents = read_csv(SOURCES["documents"])
    hewp_links_by_tender: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in read_csv(SOURCES["hewp_exact_links"]):
        hewp_links_by_tender[row["tender_id"]].append(
            {
                "place": row["village_town"],
                "areaType": row["area_type"],
                "block": row["block_name"],
                "panchayat": row["panchayat_name"],
                "department": row["department_name"],
                "division": row["division_name"],
                "estimateName": row["estimate_name"],
                "agreementName": row["agreement_name"],
                "estimateValue": number(row["estimate_cost_inr"]),
                "contractStart": row["contract_start_date"],
                "contractEnd": row["contract_end_date"],
                "agency": row["agency_name"],
                "sourceUrl": row["source_url"],
                "sourceSha256": row["source_response_sha256"],
                "linkMethod": row["link_method"],
            }
        )
    mcg_links_by_tender: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in read_csv(SOURCES["mcg_links"]):
        mcg_links_by_tender[row["tender_id"]].append(
            {
                "workId": row["mcg_work_id"],
                "workName": row["mcg_work_name"],
                "contractor": row["mcg_contractor_name"],
                "sanctionedValue": number(row["mcg_sanctioned_amount_inr"]),
                "workStart": row["mcg_work_start_date"],
                "progressPercent": number(row["mcg_progress_percent"]),
                "physicalStatus": row["mcg_physical_status"],
                "linkMethod": row["link_method"],
                "linkGrade": row["link_grade"],
                "interpretation": row["interpretation"],
            }
        )
    asset_links_by_tender: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in read_csv(SOURCES["contract_asset_links"]):
        if row["proof_grade"] != "B":
            continue
        asset_links_by_tender[row["tender_id"]].append(
            {
                "assetKey": row["logical_asset_key"],
                "component": row["work_component"],
                "coverage": row["coverage_type"],
                "proofGrade": row["proof_grade"],
                "validatorReason": row["validator_reason"],
                "evidenceSha256": row["evidence_sha256"],
            }
        )
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
        # How it was bought, alongside what was bought. See classify_modes().
        modes = classify_modes(source)
        department, department_basis = canonical_department(source)
        unit = department_unit(source)
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
            "departmentUnit": unit,
            "component": component,
            "components": components,
            "componentBasis": component_basis,
            "contractModes": modes,
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
            "hewpRecords": hewp_links_by_tender.get(tid, []),
            "mcgLinks": mcg_links_by_tender.get(tid, []),
            "assetLinks": asset_links_by_tender.get(tid, []),
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
        SHARDS_OUT / "tenders.json",
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
    places = []
    for row in read_csv(SOURCES["places"]):
        places.append(
            {
                "name": row["canonical_name"],
                "variants": row["spelling_variants"].split("|")
                if row["spelling_variants"]
                else [],
                "block": row["block_name"],
                "panchayat": row["panchayat_name"],
                "areaType": row["area_type"],
                "locationCode": row["location_code"],
                "workCount": integer(row["hewp_work_count"]) or 0,
                "awardedWorkCount": integer(row["hewp_awarded_work_count"]) or 0,
                "tenderIds": row["hewp_tender_ids"].split("|")
                if row["hewp_tender_ids"]
                else [],
                "boundaryGeometryAvailable": (
                    row["village_boundary_geometry_in_local_archive"] == "true"
                ),
                "sourceSha256": row["source_file_sha256"],
            }
        )
    write_json(OUT / "places.json", places)
    write_json(OUT / "contractors.json", contractor_output)
    for index, shard in enumerate(detail_shards):
        write_json(SHARDS_OUT / "tender-details" / f"{index:02d}.json", shard)

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
            "places": len(places),
            "hewpExactLinks": sum(len(rows) for rows in hewp_links_by_tender.values()),
            "mcgLinks": sum(len(rows) for rows in mcg_links_by_tender.values()),
            "confirmedAssetLinks": sum(
                len(rows) for rows in asset_links_by_tender.values()
            ),
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
