#!/usr/bin/env python3
"""Extract text from the document blobs that actually carry information.

WHY ONLY SOME OF THEM
---------------------
Measured across a stratified sample of the 118,079 distinct retrieved blobs, the median
text on the first two pages is:

    Technical Evaluation    30,217 docs    304 chars   first line "Signature Not Verified"
    all_stage_summary       24,199         289
    Financial Evaluation    22,926         396
    Technical Bid Opening   19,560         385
    AOC                     17,562         651
    Letter of Award          2,999       6,202        <- 10-20x richer
    Tender Document            191       3,745
    Packet / Packet Entry      425           0        <- scanned, no text layer

About 96% of the corpus is a rubber stamp: a 98 KB PDF whose entire text is "approved",
or a 166 KB one reading "As per tender term and condition", with the digital signature
block making up the rest of the file. The analytically useful content of those documents
— that the stage happened, and when — is already in tender_lifecycle_events with a
verified hash, so re-reading 64 GB to recover it would buy nothing.

So this extracts everything from the stages that carry prose, and a bounded prefix from
the stamp stages, because a minority of them are not stamps at all: `all_stage_summary`
holds corrigenda, and one of those states a tender was "re-invited due to no bid
received" — the causal reason behind the 6,198 multi-tender chains, which exists nowhere
in the structured data.

WHAT IT DOES NOT DO
-------------------
No OCR. Documents with no text layer are recorded as `no_text_layer` and counted, not
guessed at. `Packet` and `Packet Entry` are 100% scanned in sample and are the honest
OCR queue.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = Path(os.environ.get("CIVIC_STUFF", ROOT.parent / "civic-stuff"))
BLOBS = ARCHIVE / "archive" / "blobs"
DOCS = ARCHIVE / "data" / "final" / "documents.csv"
OUT = ROOT / "build" / "doctext"

# Prose stages: read in full. Stamp stages: a prefix is enough to tell a stamp from a
# corrigendum, and bounds the cost of the long tail.
FULL_STAGES = {"Letter of Award", "Tender Document", "AOC"}
PREFIX_STAGES = {"all_stage_summary", "Financial Evaluation",
                 "Technical Evaluation", "Technical Bid Opening"}
PREFIX_PAGES = 3


def extract(job: tuple[str, str, bool]) -> tuple[str, str, int, str]:
    """(sha, stage, full) -> (sha, status, chars, first_line). Runs in a worker."""
    sha, stage, full = job
    blob = BLOBS / sha
    target = OUT / sha[:2] / f"{sha}.txt"
    if target.exists():
        text = target.read_text(encoding="utf-8", errors="replace")
        first = next((l.strip() for l in text.splitlines() if l.strip()), "")
        return sha, ("cached" if text.strip() else "no_text_layer"), len(text), first[:120]
    cmd = ["pdftotext", "-layout", "-q"]
    if not full:
        cmd += ["-f", "1", "-l", str(PREFIX_PAGES)]
    cmd += [str(blob), "-"]
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        text = done.stdout or ""
    except subprocess.TimeoutExpired:
        return sha, "timeout", 0, ""
    except Exception as error:                      # noqa: BLE001 - recorded, not raised
        return sha, f"error:{type(error).__name__}", 0, ""
    if not text.strip():
        return sha, "no_text_layer", 0, ""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, target)
    first = next((l.strip() for l in text.splitlines() if l.strip()), "")
    return sha, "extracted", len(text), first[:120]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=max(2, (os.cpu_count() or 4) - 2))
    parser.add_argument("--limit", type=int, default=0, help="0 = no limit")
    parser.add_argument("--stages", default="", help="comma-separated override")
    args = parser.parse_args()

    wanted = (set(s.strip() for s in args.stages.split(",") if s.strip())
              or (FULL_STAGES | PREFIX_STAGES))

    jobs: list[tuple[str, str, bool]] = []
    seen: set[str] = set()
    stage_of: dict[str, str] = {}
    for row in csv.DictReader(open(DOCS, newline="", encoding="utf-8", errors="replace")):
        sha = (row.get("sha256") or "").strip()
        stage = row.get("stage_or_section") or ""
        if not sha or stage not in wanted or sha in seen:
            continue
        seen.add(sha)
        stage_of[sha] = stage
        jobs.append((sha, stage, stage in FULL_STAGES))
    if args.limit:
        jobs = jobs[: args.limit]

    print(f"extracting {len(jobs):,} distinct blobs across {len(wanted)} stages "
          f"on {args.workers} workers", flush=True)

    status = Counter()
    per_stage = defaultdict(lambda: {"n": 0, "chars": [], "no_text": 0})
    firsts: dict[str, Counter] = defaultdict(Counter)
    done = 0
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(extract, job): job for job in jobs}
        for future in as_completed(futures):
            sha, state, chars, first = future.result()
            stage = stage_of[sha]
            status[state] += 1
            bucket = per_stage[stage]
            bucket["n"] += 1
            if state in ("extracted", "cached"):
                bucket["chars"].append(chars)
                firsts[stage][first[:44]] += 1
            elif state == "no_text_layer":
                bucket["no_text"] += 1
            done += 1
            if done % 2000 == 0:
                print(f"  {done:,}/{len(jobs):,}  {dict(status)}", flush=True)

    report = {"jobs": len(jobs), "status": dict(status), "stages": {}}
    print(f"\n{'stage':26}{'n':>8}{'median':>9}{'p95':>9}{'max':>9}{'no text':>9}")
    for stage, bucket in sorted(per_stage.items(), key=lambda kv: -kv[1]["n"]):
        lengths = sorted(bucket["chars"])
        med = lengths[len(lengths) // 2] if lengths else 0
        p95 = lengths[int(len(lengths) * 0.95)] if lengths else 0
        mx = lengths[-1] if lengths else 0
        report["stages"][stage] = {
            "documents": bucket["n"], "with_text": len(lengths),
            "no_text_layer": bucket["no_text"],
            "median_chars": med, "p95_chars": p95, "max_chars": mx,
            "top_first_lines": firsts[stage].most_common(5),
        }
        print(f"  {stage[:24]:24}{bucket['n']:>8,}{med:>9,}{p95:>9,}{mx:>9,}"
              f"{bucket['no_text']:>9,}")
    out = ROOT / "build" / "doctext_report.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"\nstatus: {dict(status)}")
    print(f"text cached under {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
