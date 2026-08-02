#!/usr/bin/env python3
"""Incremental, resumable orchestrator for heterogeneous procurement inputs.

The portal is static, but its evidence pipeline is not.  This runner watches a
manifest of CSV/JSON/GeoJSON/text outputs, hashes only changed files, and runs
the necessary deterministic build stages.  Interrupted runs resume from the
last completed stage; source files are never edited.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CIVIC_DATA_ROOT", REPO.parent / "civic-stuff")).resolve()
STATE_PATH = REPO / "build" / "pipeline-state.json"
SOURCES = [
    ROOT / "data/final/tenders.csv",
    ROOT / "data/final/gurugram_scope.csv",
    ROOT / "data/final/documents.csv",
    ROOT / "data/final/field_provenance.csv",
    ROOT / "data/final/bid_history.csv",
    ROOT / "data/final/tender_lifecycle_events.csv",
    ROOT / "data/final/procurement_flags.csv",
    ROOT / "data/derived/award_verification_v2.csv",
    ROOT / "data/derived/procurement_chains.csv",
    ROOT / "data/derived/tender_area_index.csv",
    ROOT / "data/derived/completion_evidence_scan.csv",
]
STAGES = [
    ("analytics", [sys.executable, "scripts/build_analytics.py"]),
    ("intelligence", [sys.executable, "scripts/build_intelligence.py"]),
    # Corrections and packages sit between the builders and validation because
    # validation reads tender-index.json — which only the package builder writes.
    # Without these two stages the pipeline validated a stale index, or none at all.
    ("corrections", [sys.executable, "scripts/build_value_corrections.py"]),
    ("packages", [sys.executable, "scripts/build_tender_packages.py"]),
    ("validation", [sys.executable, "scripts/validate_analytics.py"]),
    ("tests", ["npm", "test"]),
    ("web", ["npm", "run", "build"]),
]


def read_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"sources": {}, "completed": [], "runs": []}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def write_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_PATH.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(state, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(STATE_PATH)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


async def inspect_source(path: Path, previous: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    stat = path.stat()
    key = str(path)
    old = previous.get(key, {})
    if old.get("bytes") == stat.st_size and old.get("mtimeNs") == stat.st_mtime_ns:
        return key, old
    digest = await asyncio.to_thread(sha256, path)
    return key, {
        "bytes": stat.st_size,
        "mtimeNs": stat.st_mtime_ns,
        "sha256": digest,
    }


async def fingerprint(previous: dict[str, Any]) -> dict[str, Any]:
    missing = [str(path) for path in SOURCES if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing pipeline sources:\n" + "\n".join(missing))
    results = await asyncio.gather(
        *(inspect_source(path, previous) for path in SOURCES)
    )
    return dict(results)


def run_stage(name: str, command: list[str], state: dict[str, Any]) -> None:
    state["activeStage"] = name
    write_state(state)
    subprocess.run(command, cwd=REPO, check=True)
    state["completed"].append(name)
    state["activeStage"] = None
    write_state(state)


async def run_once(force: bool) -> bool:
    state = read_state()
    current_sources = await fingerprint(state.get("sources", {}))
    sources_changed = current_sources != state.get("sources", {})
    stage_names = [name for name, _ in STAGES]
    completed = [
        name for name in state.get("completed", []) if name in stage_names
    ]
    if not force and not sources_changed and completed == stage_names:
        print("No source changes; pipeline is already current.")
        return False

    # A source change invalidates every derived stage. If the sources are
    # unchanged after an interruption, preserve the completed prefix and resume
    # at the first unfinished stage.
    if force or sources_changed:
        completed = []

    state["sources"] = current_sources
    state["completed"] = completed
    state["activeStage"] = None
    state["startedAt"] = datetime.now(timezone.utc).isoformat()
    write_state(state)
    try:
        for name, command in STAGES:
            if name in state["completed"]:
                print(f"Skipping completed stage: {name}")
                continue
            run_stage(name, command, state)
    except BaseException as error:
        state["lastError"] = f"{type(error).__name__}: {error}"
        state["failedAt"] = datetime.now(timezone.utc).isoformat()
        write_state(state)
        raise
    state["completedAt"] = datetime.now(timezone.utc).isoformat()
    state["lastError"] = None
    state.setdefault("runs", []).append(
        {
            "startedAt": state["startedAt"],
            "completedAt": state["completedAt"],
            "sourceCount": len(current_sources),
        }
    )
    state["runs"] = state["runs"][-20:]
    write_state(state)
    return True


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=float, default=60.0)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    await run_once(args.force)
    while args.watch:
        await asyncio.sleep(max(args.interval, 5.0))
        try:
            await run_once(False)
        except Exception as error:
            print(f"pipeline error: {error}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
