#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parent.parent
EXE = REPO_ROOT / "src" / "aquacrop"


def run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=str(cwd), check=True)


def run_aquacrop(case_dir: Path) -> None:
    if not EXE.exists():
        raise FileNotFoundError(f"Expected executable at {EXE}")
    subprocess.run([str(EXE)], cwd=str(case_dir), check=True)


def sha256_normalized_out(path: Path) -> str:
    data = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if data and data[0].startswith("AquaCrop"):
        data = data[1:]
    normalized = "\n".join(data).encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


def smoke_test() -> None:
    case_dir = REPO_ROOT / "examples" / "canterbury_dairy_grass"
    run_aquacrop(case_dir)
    outp = case_dir / "OUTP"
    required = [
        outp / "CanterburyDairyGrassPRMday.OUT",
        outp / "CanterburyDairyGrassPRMseason.OUT",
        outp / "CanterburyDairyGrassPRMharvests.OUT",
    ]
    missing = [p for p in required if not p.exists() or p.stat().st_size == 0]
    if missing:
        raise RuntimeError(f"Smoke test missing outputs: {missing}")


def deterministic_test() -> None:
    case_dir = REPO_ROOT / "tests" / "canterbury_deterministic"
    run_aquacrop(case_dir)
    outp = case_dir / "OUTP"
    targets = {
        "season": outp / "CanterburyDeterministicPRMseason.OUT",
        "harvests": outp / "CanterburyDeterministicPRMharvests.OUT",
        "irr": outp / "CanterburyDeterministicPRMirrInfo.OUT",
    }
    for k, p in targets.items():
        if not p.exists():
            raise RuntimeError(f"Deterministic test missing {k} output: {p}")

    # Filled in by the initial run (see developer docs in this repo).
    expected = {
        "season": "d3a55230e79ddc685b05e91070096aca64d3558fa728674220070b66835e551b",
        "harvests": "8ae24fc2be3f323e7b3f84a06f343f03e90b73fdc69c7037c10811c51e3e0eb7",
        "irr": "4643561e52119a8df891db211fccd94d3d6cfe1de480dbc9d070c72f391b36af",
    }
    actual = {k: sha256_normalized_out(p) for k, p in targets.items()}

    unset = [k for k, v in expected.items() if not v]
    if unset:
        raise RuntimeError(
            "Deterministic hashes are not set yet. "
            f"Run once and set expected hashes for: {unset}. "
            f"Actual: {actual}"
        )

    mismatches = {k: (expected[k], actual[k]) for k in expected if expected[k] != actual[k]}
    if mismatches:
        raise RuntimeError(f"Deterministic regression mismatch: {mismatches}")


def main() -> int:
    run(["make"], cwd=REPO_ROOT / "src")
    smoke_test()
    deterministic_test()
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
