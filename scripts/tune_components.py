#!/usr/bin/env python3
"""Iterate the component classifier against the real descriptions until it stops paying.

The classifier is a living rule set, not a fixed table: these are 49,121 free-text
descriptions written by dozens of offices over fifteen years, with no controlled
vocabulary, and every pass over the residue turns up shorthand the last pass missed.

This harness exists so a change to COMPONENTS can be judged rather than guessed at. It
reports, for a candidate rule set:

  * the unclassified rate, which is the headline;
  * what each new rule actually caught, so a rule that fires on nothing gets deleted;
  * COLLISIONS — descriptions matching several components — because a rule that steals
    work from a better rule makes the classification worse while making the
    unclassified rate look better;
  * the top remaining unmatched terms, which is the worklist for the next pass.

Run it, read the residue, add rules, run it again.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import os
import re
import sys
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = Path(os.environ.get("CIVIC_STUFF", ROOT.parent / "civic-stuff"))
TENDERS = ARCHIVE / "data" / "final" / "tenders.csv"

# ── THE RULE SET ─────────────────────────────────────────────────────────────────
# Order matters: the first match wins, so the more specific work type is listed before
# the generic surface it sits on. Every abbreviation here was read out of the residue of
# a previous pass, and the comment says what it stands for, because none of these are
# guessable by someone who has not seen a Haryana estimate.
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


# ── CONTRACT MODES, WHICH ARE NOT WORK TYPES ─────────────────────────────────────
# "Annual maintenance of parks" is landscape work bought under a maintenance contract,
# and "Hiring of a water tanker" is water work bought as hired capacity. Modelling these
# as COMPONENTS forced a false choice: 1,375 descriptions matched landscape+maintenance
# and 318 matched maintenance+surface, and in every one the classifier had to discard a
# true fact in order to record another true fact. They are orthogonal to the work type,
# so they are recorded ALONGSIDE the component instead of competing with it.
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


def build(rules):
    return [(name, re.compile(pattern, re.I)) for name, pattern in rules]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--residue", type=int, default=30,
                        help="how many unmatched terms to print as the next worklist")
    args = parser.parse_args()

    rx = build(COMPONENTS)
    mode_patterns = build(MODES)
    modes_seen = collections.Counter()
    rows = list(csv.DictReader(open(TENDERS, newline="", encoding="utf-8",
                                    errors="replace")))

    counts = collections.Counter()
    first_hit = collections.Counter()
    collisions = collections.Counter()
    unmatched_terms = collections.Counter()
    unmatched_examples = []

    for row in rows:
        description = row.get("work_description", "") or ""
        hits = [name for name, pattern in rx if pattern.search(description)]
        if not hits:
            title = row.get("title", "") or ""
            hits = [name for name, pattern in rx if pattern.search(title)]
        for mode_name, mode_rx in mode_patterns:
            if mode_rx.search(description) or mode_rx.search(row.get("title", "") or ""):
                modes_seen[mode_name] += 1
        if hits:
            first_hit[hits[0]] += 1
            counts["classified"] += 1
            if len(hits) > 1:
                collisions[" + ".join(sorted(hits[:3]))] += 1
        else:
            category = (row.get("tender_category", "") or "").lower()
            if category in ("goods", "services"):
                first_hit[category] += 1
                counts["classified_by_portal_category"] += 1
            else:
                counts["unclassified"] += 1
                if len(unmatched_examples) < 40:
                    unmatched_examples.append(description[:96] or "(empty)")
                for term in re.findall(r"[A-Za-z]{3,}", description.lower()):
                    if term not in STOP:
                        unmatched_terms[term] += 1

    total = len(rows)
    unclassified = counts["unclassified"]
    print(f"tenders                {total:,}")
    print(f"classified by rule     {counts['classified']:,}")
    print(f"by portal category     {counts['classified_by_portal_category']:,}")
    print(f"UNCLASSIFIED           {unclassified:,}  ({unclassified / total * 100:.1f}%)")
    print(f"                       baseline was 21,470 (43.7%)\n")

    print("component distribution:")
    for name, count in first_hit.most_common():
        print(f"   {name:16} {count:>7,}  {count / total * 100:>5.1f}%")

    print(f"\ncontract modes — recorded ALONGSIDE the component, not instead of it:")
    for name, count in modes_seen.most_common():
        print(f"   {name:16} {count:>7,}  {count / total * 100:>5.1f}%")

    print(f"\ncollisions — descriptions matching several rules (first wins):")
    for pair, count in collisions.most_common(8):
        print(f"   {pair:44} {count:>6,}")

    print(f"\nnext worklist — commonest words still unmatched:")
    terms = ", ".join(f"{t} ({n:,})" for t, n in unmatched_terms.most_common(args.residue))
    print(f"   {terms}")
    print(f"\nstill-unmatched examples:")
    for example in unmatched_examples[:10]:
        print(f"   {example!r}")

    report = {
        "tenders": total,
        "unclassified": unclassified,
        "unclassifiedPct": round(unclassified / total * 100, 2),
        "distribution": dict(first_hit.most_common()),
        "collisions": dict(collisions.most_common(20)),
        "residueTerms": dict(unmatched_terms.most_common(60)),
    }
    out = ROOT / "build" / "component_tuning.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


STOP = {
    "work", "works", "the", "and", "for", "with", "from", "under", "various", "other",
    "gurugram", "haryana", "distt", "district", "village", "block", "sector", "ward",
    "zone", "division", "constituency", "year", "estimate", "providing", "provision",
    "const", "construction", "near", "road", "roads", "street", "streets", "house",
    "gram", "panchayat", "including", "etc", "nos", "no", "sub", "part", "phase",
    "area", "areas", "site", "sites", "line", "lines", "laying", "fixing", "supply",
    "repair", "repairing", "maintenance", "annual", "new", "old", "main", "link",
}

if __name__ == "__main__":
    raise SystemExit(main())
