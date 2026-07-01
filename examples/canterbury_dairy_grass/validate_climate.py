#!/usr/bin/env python3

from __future__ import annotations

import argparse
import calendar
from dataclasses import dataclass
import datetime as dt
from pathlib import Path
import sys


@dataclass(frozen=True)
class ClimHeader:
    description: str
    record_type: int
    first_day: int
    first_month: int
    first_year: int
    data_lines: list[str]


def _parse_int_prefix(line: str, label: str, path: Path) -> int:
    try:
        return int(line.strip().split()[0])
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"{path}: cannot parse {label} from line: {line!r}") from exc


def read_climate_file(path: Path) -> ClimHeader:
    if not path.exists():
        raise FileNotFoundError(str(path))

    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(lines) < 8:
        raise ValueError(f"{path}: too few lines ({len(lines)})")

    description = lines[0].rstrip("\n")
    record_type = _parse_int_prefix(lines[1], "record type", path)
    first_day = _parse_int_prefix(lines[2], "first day", path)
    first_month = _parse_int_prefix(lines[3], "first month", path)
    first_year = _parse_int_prefix(lines[4], "first year", path)

    sep_idx = None
    for i, line in enumerate(lines):
        if line.strip().startswith("=") and len(line.strip()) >= 5:
            sep_idx = i
            break
    if sep_idx is None:
        raise ValueError(f"{path}: could not find data separator line of '=' characters")

    data_lines = [ln.strip() for ln in lines[sep_idx + 1 :] if ln.strip()]
    if not data_lines:
        raise ValueError(f"{path}: no data lines found after separator")

    return ClimHeader(
        description=description,
        record_type=record_type,
        first_day=first_day,
        first_month=first_month,
        first_year=first_year,
        data_lines=data_lines,
    )


def expected_daily_count(first_year: int, first_month: int, first_day: int) -> int:
    # AquaCrop climate inputs typically provide one continuous year of daily records.
    # Support any start date (e.g., Jul-1 to Jun-30 for Southern Hemisphere “hydrologic years”).
    if first_year == 1901:
        return 365
    try:
        start = dt.date(first_year, first_month, first_day)
        end_exclusive = dt.date(first_year + 1, first_month, first_day)
    except ValueError as exc:
        raise ValueError(f"invalid start date {first_year:04d}-{first_month:02d}-{first_day:02d}") from exc
    return (end_exclusive - start).days


def validate_tnx(path: Path) -> list[str]:
    problems: list[str] = []
    h = read_climate_file(path)

    if h.record_type != 1:
        problems.append(f"{path}: record type must be 1 (daily), got {h.record_type}")

    try:
        n_expected = expected_daily_count(h.first_year, h.first_month, h.first_day)
    except Exception as exc:  # noqa: BLE001
        problems.append(f"{path}: cannot determine expected day count: {exc}")
        n_expected = None

    if n_expected is not None and len(h.data_lines) != n_expected:
        problems.append(f"{path}: expected {n_expected} daily records, found {len(h.data_lines)}")

    for i, line in enumerate(h.data_lines, start=1):
        parts = line.replace("\t", " ").split()
        if len(parts) < 2:
            problems.append(f"{path}: day {i}: expected Tmin Tmax, got: {line!r}")
            continue
        try:
            tmin = float(parts[0])
            tmax = float(parts[1])
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{path}: day {i}: cannot parse Tmin/Tmax: {line!r} ({exc})")
            continue
        if tmax < tmin:
            problems.append(f"{path}: day {i}: Tmax < Tmin ({tmax} < {tmin})")
        if not (-25.0 <= tmin <= 45.0) or not (-25.0 <= tmax <= 55.0):
            problems.append(f"{path}: day {i}: suspicious temperature range Tmin={tmin}, Tmax={tmax}")
    return problems


def validate_series_1col(path: Path, label: str, min_ok: float, max_ok: float) -> list[str]:
    problems: list[str] = []
    h = read_climate_file(path)

    if h.record_type != 1:
        problems.append(f"{path}: record type must be 1 (daily), got {h.record_type}")

    try:
        n_expected = expected_daily_count(h.first_year, h.first_month, h.first_day)
    except Exception as exc:  # noqa: BLE001
        problems.append(f"{path}: cannot determine expected day count: {exc}")
        n_expected = None

    if n_expected is not None and len(h.data_lines) != n_expected:
        problems.append(f"{path}: expected {n_expected} daily records, found {len(h.data_lines)}")

    for i, line in enumerate(h.data_lines, start=1):
        try:
            v = float(line.split()[0])
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{path}: day {i}: cannot parse {label}: {line!r} ({exc})")
            continue
        if v < min_ok or v > max_ok:
            problems.append(f"{path}: day {i}: {label}={v} outside [{min_ok}, {max_ok}] (units?)")
    return problems


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Validate AquaCrop climate file formatting for daily .Tnx/.ETo/.PLU inputs. "
            "Checks day count, basic unit sanity, and Tmin/Tmax ordering."
        )
    )
    ap.add_argument("tnx", type=Path, help="Temperature file (*.Tnx) with daily Tmin/Tmax")
    ap.add_argument("eto", type=Path, help="Reference ET0 file (*.ETo) with daily values (mm/day)")
    ap.add_argument("plu", type=Path, help="Rainfall file (*.PLU) with daily totals (mm/day)")
    args = ap.parse_args(argv)

    problems: list[str] = []
    problems.extend(validate_tnx(args.tnx))
    problems.extend(validate_series_1col(args.eto, "ETo", 0.0, 15.0))
    problems.extend(validate_series_1col(args.plu, "Rain", 0.0, 200.0))

    if problems:
        for p in problems:
            print(p, file=sys.stderr)
        return 2

    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
