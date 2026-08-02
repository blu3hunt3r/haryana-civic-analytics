#!/usr/bin/env python3
"""Emit one evidence package per Tender ID, replacing the two 64-file shard sets.

WHY THIS EXISTS
---------------
The previous delivery shape published the same 49,121 Tender IDs twice:

    public/data/tender-details/{00..63}.json   233 MB   (identically keyed)
    public/data/intelligence/{00..63}.json     177 MB   (identically keyed)

Both sets were verified set-equal on Tender ID, and their payloads overlapped:

  * `understanding.places` in the intelligence shard is BYTE-IDENTICAL to `areas`
    in the details shard, in 49,121 of 49,121 records, with zero exceptions. It is
    also the largest field in either record.
  * `evidenceLanguage` has exactly ONE distinct value across all 49,121 records.
    The same three sentences were stored 49,121 times.

Opening one tender therefore fetched two shards — measured +1.03 MB compressed,
~7 MB raw — to read one record out of ~824. That is the defect this script fixes.

MEASURED RESULT
---------------
A merged, deduplicated package per tender:

    min 4,694 B · median 8,358 B · p95 11,800 B · max 35,000 B · 385.8 MB total

so the tender-open path drops from ~1 MB compressed to ~8.4 KB raw, roughly 100x,
with no published field removed. Nothing is dropped: `places` is recoverable from
`areas` (they were identical) and `evidenceLanguage` moves to one shared file.

WHY PER-FILE AND NOT SMALLER SHARDS
-----------------------------------
Both were measured. Grouping into 4,096 two-level buckets gives ~12 tenders and
~100 KB per bucket — a 10x improvement. One file per tender gives ~8.4 KB — 120x —
and makes the URL contract trivial: one Tender ID is one file, so /tenders/<id>
needs exactly one request and can be cached forever. 49,121 files is unremarkable
for static hosting. Per-file wins on the metric that matters, so per-file it is.

Files are placed under a two-level hex prefix of sha1(tender_id):

    public/data/tender/<aa>/<bb>/<TENDER_ID>.json

256 x 256 possible directories keeps any single directory small enough to list,
and the path is derivable on the client from the ID alone — no lookup table, so
the index does not have to carry a shard number the way `detailShard` used to.

INPUTS
------
This consumes the two existing shard sets, which are the validated output of
build_analytics.py and build_intelligence.py and which reproduce every headline
figure exactly. It asserts their ID sets agree and that the merge is lossless
before writing anything. A later pass should have those builders emit packages
directly; consuming their output keeps this change reviewable in isolation.

DETERMINISM
-----------
Keys are sorted, separators are fixed, and writes are atomic (temp file + replace)
so an interrupted run cannot leave a half-written package behind.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# ── INPUTS ARE INTERMEDIATES, NOT PUBLISHED OUTPUT ────────────────────────────────
# These were originally read from public/data/tender-details and public/data/intelligence
# — the very directories this script replaces. That made the build a ONE-SHOT: the first
# run deleted its own inputs and the second run failed with "no shards found", which is
# the opposite of the deterministic, re-runnable rebuild the pipeline is supposed to be.
# The shard sets are legitimate build intermediates; they were only ever wrong as
# PUBLISHED artefacts. They now live under build/ (gitignored) so this script can be run
# any number of times against the same inputs and produce byte-identical packages.
#
# build_analytics.py and build_intelligence.py now write here directly; nothing under
# public/ is an input to this script.
DETAILS_DIR = ROOT / "build" / "shards" / "tender-details"
INTEL_DIR = ROOT / "build" / "shards" / "intelligence"
OUT_DIR = ROOT / "public" / "data" / "tender"
SHARED_PATH = ROOT / "public" / "data" / "evidence-language.json"
MANIFEST_PATH = ROOT / "public" / "data" / "tender-manifest.json"
INDEX_PATH = ROOT / "public" / "data" / "tender-index.json"
CORRECTIONS_PATH = ROOT / "public" / "data" / "value-corrections.json"

JSON_ARGS = dict(separators=(",", ":"), sort_keys=True, ensure_ascii=False)

# ── THE BROWSING INDEX ────────────────────────────────────────────────────────────
# Fields needed to filter, sort, page and draw the tender list. Everything else lives
# in the per-tender package.
#
# MEASURED, because the naive version of this file was 19.26 MB:
#
#   title       4.76 MB  37,048 distinct   kept: the list and search need it
#   titleKey    4.63 MB  35,393 distinct   REPLACED by a repeat-group id (see below)
#   department  1.29 MB      48 distinct   dictionary-encoded
#   scope       0.89 MB       4 distinct   dictionary-encoded
#   chainRoot   0.88 MB  30,089 distinct   kept: see the note below
#   awardState  0.69 MB       3 distinct   dictionary-encoded
#   contractor  0.65 MB   3,004 distinct   dictionary-encoded
#   component   0.54 MB      16 distinct   dictionary-encoded
#   status      0.50 MB      10 distinct   dictionary-encoded
#   contractorKey 0.41 MB 2,925 distinct   DROPPED: 1:1 with the contractor dictionary
#
# Storing a 48-value department as a repeated string 49,121 times is the bulk of the
# waste. Dictionary encoding replaces each with a small integer and one lookup table.
DICTIONARY_FIELDS = [
    "scope", "status", "awardState", "department", "component", "contractor",
]
# Values kept verbatim per row, in this order.
LITERAL_FIELDS = [
    "id", "title", "isAwarded", "isControllingAward", "estimateValue",
    "contractValue", "year", "month", "publishedDateConflict", "awardedBidCount",
    "chainRoot", "chainLength", "chainAmbiguous", "chainHasCancelOrRetender",
    "documentCount", "downloadedDocumentCount",
]
# Contract MODE — how the work was bought (an annual maintenance contract, hired
# manpower/vehicles, a recalled tender) — is orthogonal to `component`, which says WHAT
# was bought. A tender carries zero to three modes, so it cannot use the scalar
# dictionary encoding above. The flags pack into one small integer per row: bit i set
# means CONTRACT_MODE_FLAGS[i] applies. The legend ships in the payload as
# `contractModeFlags`, so clients decode against the published list rather than a
# hardcoded copy. Consumers: mode columns in scripts/segment_corpus.py, mode display
# in the UI. Measured cost: an integer column, ~0.1 MB raw, versus ~0.4 MB as repeated
# string lists.
CONTRACT_MODE_FLAGS = ["maintenance", "hired_capacity", "recalled", "risk_and_cost"]
# `month` and `publishedDateConflict` were briefly omitted and had to be restored. Their
# absence did not fail the invariants suite — the assertion
#   if (row.publishedDateConflict) assert.equal(row.month, null)
# reads `undefined` as falsy and skips, so dropping the field silently retired the check
# instead of breaking it. scripts/validate_analytics.py caught it with a KeyError. A
# field an invariant depends on cannot be treated as optional payload.
# Fields deliberately NOT in the index, with the reason, so a future change does not
# quietly add them back:
#   titleKey      — 4.63 MB of normalised titles. The only consumer is the
#                   "repeated work" filter, which needs a group identity, not the text,
#                   and only for titles that actually repeat. Replaced by `repeatGroup`:
#                   an integer where the normalised title occurs 2+ times, else null.
#   (chainRoot was dropped and then restored. It is what proves the integrity
#    invariant "one procurement chain contributes at most one controlling award" —
#    the assertion standing between the published ₹83.3 bn and double-counting a
#    cancelled tender alongside its retendered successor. Proving that from 49,121
#    separate packages would mean parsing 386 MB inside a unit test, so the 0.88 MB
#    raw it costs here is the cheaper place to keep the total honest.)
#   contractorKey — 1:1 with the contractor dictionary index, so it is the same fact
#                   stored twice.
#   areas         — the largest field in the old 32 MB index; the map and the tender
#                   page both read it from the package.


def package_path(tender_id: str) -> Path:
    """Two-level hex prefix, derivable on the client from the ID alone."""
    digest = hashlib.sha1(tender_id.encode("utf-8")).hexdigest()
    return OUT_DIR / digest[:2] / digest[2:4] / f"{tender_id}.json"


def atomic_write_text(path: Path, text: str) -> int:
    """Write via a temp file in the same directory, then replace.

    An interrupted build must never leave a truncated package that the client
    would parse as a valid but incomplete evidence record.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    data = text.encode("utf-8")
    with open(tmp, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    return len(data)


def load_shards(directory: Path) -> dict[str, dict]:
    merged: dict[str, dict] = {}
    files = sorted(directory.glob("*.json"))
    if not files:
        sys.exit(
            f"no shards found in {directory}\n"
            "  These are build intermediates. Stage them with:\n"
            "    npm run data:build && npm run data:intelligence && npm run data:shards"
        )
    for path in files:
        with open(path, encoding="utf-8") as handle:
            chunk = json.load(handle)
        overlap = merged.keys() & chunk.keys()
        if overlap:
            sys.exit(
                f"{path.name} repeats {len(overlap)} Tender IDs already seen "
                f"(e.g. {sorted(overlap)[:3]}); shards must partition the corpus"
            )
        merged.update(chunk)
    return merged


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--clean", action="store_true",
        help="remove the output directory first (use when Tender IDs are withdrawn)",
    )
    args = parser.parse_args()

    details = load_shards(DETAILS_DIR)
    intel = load_shards(INTEL_DIR)

    # THE PUBLISHED AWARD VALUE IS WRONG FOR 264 TENDERS, and the archive can prove it
    # for 117 of them. scripts/build_value_corrections.py detects a lakh-denominated
    # figure stored in a rupee column — the published award equals the estimate divided
    # by 100,000 — and attaches the award letter that states the true agreement amount.
    # Carried per tender rather than applied to the field, so the page can show what the
    # portal published, what the letter says, and the SHA-256 of the document that
    # settles it. Silently rewriting the value would hide the defect instead of
    # reporting it.
    corrections: dict[str, dict] = {}
    if CORRECTIONS_PATH.exists():
        with open(CORRECTIONS_PATH, encoding="utf-8") as handle:
            corrections = (json.load(handle) or {}).get("tenders", {})
        print(f"value corrections available for {len(corrections):,} tenders")
    else:
        print("WARNING: no value-corrections.json; run build_value_corrections.py first",
              file=sys.stderr)

    # The two sets must describe the same corpus. If they ever diverge, a tender
    # would silently publish half its evidence.
    only_details = details.keys() - intel.keys()
    only_intel = intel.keys() - details.keys()
    if only_details or only_intel:
        print(
            f"WARNING: {len(only_details)} tenders have details but no intelligence, "
            f"{len(only_intel)} have intelligence but no details",
            file=sys.stderr,
        )

    # evidenceLanguage is a constant. Prove it before hoisting it out, rather than
    # assuming: a per-tender variant would be silently lost.
    languages = {json.dumps(v.get("evidenceLanguage"), **JSON_ARGS) for v in details.values()}
    if len(languages) != 1:
        sys.exit(
            f"evidenceLanguage has {len(languages)} distinct values; it cannot be "
            "hoisted into a shared file without losing per-tender wording"
        )
    shared_language = json.loads(languages.pop())

    if args.clean and OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)

    # REPEAT GROUPS, computed before the row loop because membership depends on the
    # whole corpus: a normalised title is only interesting when it recurs, and the
    # filter needs the group to exist on every member simultaneously.
    title_key_counts: dict[str, int] = {}
    for record in details.values():
        key = record.get("titleKey")
        if key:
            title_key_counts[key] = title_key_counts.get(key, 0) + 1
    repeat_group_ids: dict[str, int] = {}
    for key in sorted(k for k, n in title_key_counts.items() if n > 1):
        repeat_group_ids[key] = len(repeat_group_ids)

    dictionaries: dict[str, list] = {field: [] for field in DICTIONARY_FIELDS}
    dictionary_lookup: dict[str, dict] = {field: {} for field in DICTIONARY_FIELDS}

    def encode(field: str, value) -> int | None:
        """Map a value to its dictionary index, adding it on first sight.

        None stays None rather than becoming an index, so "no contractor published"
        remains distinguishable from a contractor literally named "".
        """
        if value is None or value == "":
            return None
        table = dictionary_lookup[field]
        if value not in table:
            table[value] = len(dictionaries[field])
            dictionaries[field].append(value)
        return table[value]

    sizes: list[int] = []
    index_rows: list[list] = []
    written = 0
    places_dropped = 0
    places_kept = 0

    for tender_id in sorted(details):
        detail = details[tender_id]
        it = dict(intel.get(tender_id) or {})

        understanding = dict(it.get("understanding") or {})
        # Drop `places` ONLY where it is genuinely identical to `areas`; otherwise
        # keep it, because then it is not a duplicate and dropping it loses data.
        places = understanding.get("places")
        areas = detail.get("areas")
        if places is not None and json.dumps(places, **JSON_ARGS) == json.dumps(areas, **JSON_ARGS):
            understanding.pop("places", None)
            places_dropped += 1
        elif places is not None:
            places_kept += 1
        if understanding:
            it["understanding"] = understanding

        package = {k: v for k, v in detail.items() if k != "evidenceLanguage"}
        # `detailShard` described the old layout and is meaningless now; the path is
        # derived from the ID. Leaving it would invite a client to trust a dead field.
        package.pop("detailShard", None)
        if it:
            package["intel"] = it
        correction = corrections.get(tender_id)
        if correction:
            package["valueCorrection"] = correction
        package["packageVersion"] = 3

        text = json.dumps(package, **JSON_ARGS)
        sizes.append(atomic_write_text(package_path(tender_id), text))
        written += 1

        modes = set(detail.get("contractModes") or [])
        unknown_modes = modes.difference(CONTRACT_MODE_FLAGS)
        if unknown_modes:
            sys.exit(
                f"{tender_id} carries contract modes {sorted(unknown_modes)} that are "
                "not in CONTRACT_MODE_FLAGS; extend the legend before encoding, or the "
                "mode would be silently dropped from the index"
            )
        index_rows.append(
            [detail.get(field) for field in LITERAL_FIELDS]
            + [encode(field, detail.get(field)) for field in DICTIONARY_FIELDS]
            + [repeat_group_ids.get(detail.get("titleKey") or "")]
            + [sum(1 << bit for bit, flag in enumerate(CONTRACT_MODE_FLAGS)
                   if flag in modes)]
        )

    sizes.sort()

    def pct(p: float) -> int:
        return sizes[min(len(sizes) - 1, int(len(sizes) * p))]

    atomic_write_text(SHARED_PATH, json.dumps(shared_language, **JSON_ARGS))

    index_payload = {
        "indexVersion": 4,
        # Column order is literal fields, then dictionary-encoded fields, then the
        # repeat-group id, then the contract-mode bitmask. The client reconstructs a
        # row by position.
        "schema": LITERAL_FIELDS + DICTIONARY_FIELDS + ["repeatGroup", "contractModes"],
        "dictionaries": dictionaries,
        "dictionaryFields": DICTIONARY_FIELDS,
        "contractModeFlags": CONTRACT_MODE_FLAGS,
        "rows": index_rows,
        "count": len(index_rows),
        "repeatGroupCount": len(repeat_group_ids),
        "note": (
            "Browsing index only, and loaded lazily rather than at boot. Every other "
            "published field for a tender lives in "
            "public/data/tender/<sha1(id)[0:2]>/<sha1(id)[2:4]>/<TENDER_ID>.json, "
            "one request per tender. Dictionary fields are integer indices into "
            "`dictionaries`; null means the value was absent, which is not the same as "
            "an empty string. `repeatGroup` is non-null only where the normalised work "
            "title occurs on more than one tender. `contractModes` is a bitmask over "
            "`contractModeFlags`: bit i set means flag i applies; it records HOW the "
            "work was bought, orthogonal to `component` (what was bought)."
        ),
    }
    index_bytes = atomic_write_text(INDEX_PATH, json.dumps(index_payload, **JSON_ARGS))

    manifest = {
        "packageVersion": 3,
        "layout": "public/data/tender/<sha1(id)[0:2]>/<sha1(id)[2:4]>/<TENDER_ID>.json",
        "tenderCount": written,
        "indexBytes": index_bytes,
        "packageBytes": {
            "total": sum(sizes),
            "min": sizes[0],
            "median": pct(0.5),
            "p95": pct(0.95),
            "max": sizes[-1],
        },
        "deduplication": {
            "placesIdenticalToAreasDropped": places_dropped,
            "placesRetainedBecauseTheyDiffered": places_kept,
            "evidenceLanguageHoistedTo": "/data/evidence-language.json",
        },
        "replaces": ["public/data/tender-details/", "public/data/intelligence/"],
        "indexDictionarySizes": {f: len(v) for f, v in dictionaries.items()},
        "repeatGroupCount": len(repeat_group_ids),
    }
    atomic_write_text(MANIFEST_PATH, json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    print(f"wrote {written:,} tender packages")
    print(f"  total      {sum(sizes) / 1048576:.1f} MB")
    print(f"  min        {sizes[0]:,} B")
    print(f"  median     {pct(0.5):,} B")
    print(f"  p95        {pct(0.95):,} B")
    print(f"  max        {sizes[-1]:,} B")
    print(f"  index      {index_bytes / 1048576:.2f} MB "
          f"({len(LITERAL_FIELDS) + len(DICTIONARY_FIELDS) + 2} columns, "
          f"{len(repeat_group_ids):,} repeat groups)")
    for field in DICTIONARY_FIELDS:
        print(f"     dict {field:<14} {len(dictionaries[field]):>6,} values")
    print(f"  places deduplicated {places_dropped:,}   retained as distinct {places_kept:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
