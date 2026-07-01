#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path
import sys

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np


@dataclass(frozen=True)
class WaterInputs:
    dates: list[dt.date]
    rain_mm: np.ndarray
    irri_mm: np.ndarray


def read_prmday_rain_irri(path: Path) -> WaterInputs:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()

    header_i = None
    for i, line in enumerate(lines):
        if re.match(r"\s*Day\s+Month\s+Year\b", line):
            header_i = i
            break
    if header_i is None:
        raise ValueError(f"{path}: could not find PRMday header line starting with 'Day Month Year'")

    cols = lines[header_i].split()
    want = ["Day", "Month", "Year", "Rain", "Irri"]
    missing = [c for c in want if c not in cols]
    if missing:
        raise ValueError(f"{path}: missing expected columns: {missing}")

    col_idx = {c: cols.index(c) for c in want}

    dates: list[dt.date] = []
    rain: list[float] = []
    irri: list[float] = []

    # Data starts after the units line.
    for line in lines[header_i + 2 :]:
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) <= max(col_idx.values()):
            continue
        try:
            day = int(parts[col_idx["Day"]])
            month = int(parts[col_idx["Month"]])
            year = int(parts[col_idx["Year"]])
            dates.append(dt.date(year, month, day))
            rain.append(float(parts[col_idx["Rain"]]))
            irri.append(float(parts[col_idx["Irri"]]))
        except Exception:  # noqa: BLE001
            continue

    if not dates:
        raise ValueError(f"{path}: no data rows parsed")

    return WaterInputs(
        dates=dates,
        rain_mm=np.asarray(rain, dtype=float),
        irri_mm=np.asarray(irri, dtype=float),
    )


def _plot_daily_bars(
    dates: list[dt.date],
    values: np.ndarray,
    *,
    title: str,
    ylabel: str,
    color: str,
    out: Path,
) -> None:
    x = [dt.datetime(d.year, d.month, d.day) for d in dates]

    fig, ax = plt.subplots(figsize=(14, 5))
    ax.bar(x, values, width=0.95, color=color, alpha=0.7, edgecolor="none")

    ax.set_title(title)
    ax.set_xlabel("Date")
    ax.set_ylabel(ylabel)
    ax.grid(True, axis="y", alpha=0.25)

    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))

    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description="Plot daily rainfall + irrigation bar charts from AquaCrop PRMday output."
    )
    ap.add_argument(
        "--prmday",
        type=Path,
        default=None,
        help="Path to *PRMday.OUT (default: first match in OUTP/*PRMday.OUT in current dir)",
    )
    ap.add_argument("--rain-out", type=Path, default=Path("OUTP/rainfall_by_day.png"))
    ap.add_argument("--irri-out", type=Path, default=Path("OUTP/irrigation_applied_by_day.png"))
    args = ap.parse_args(argv)

    prmday = args.prmday
    if prmday is None:
        matches = sorted(Path("OUTP").glob("*PRMday.OUT"))
        if not matches:
            raise SystemExit("No --prmday provided and no OUTP/*PRMday.OUT found in current dir")
        prmday = matches[0]

    s = read_prmday_rain_irri(prmday)

    rain_total = float(np.nansum(s.rain_mm))
    irri_total = float(np.nansum(s.irri_mm))
    irri_events = int(np.sum(s.irri_mm > 0))

    _plot_daily_bars(
        s.dates,
        s.rain_mm,
        title=f"Daily rainfall (mm/day) — total={rain_total:.1f} mm",
        ylabel="Rainfall (mm/day)",
        color="tab:blue",
        out=args.rain_out,
    )

    _plot_daily_bars(
        s.dates,
        s.irri_mm,
        title=f"Daily irrigation applied (mm/day) — total={irri_total:.1f} mm, events={irri_events}",
        ylabel="Irrigation applied (mm/day)",
        color="tab:green",
        out=args.irri_out,
    )

    print(args.rain_out)
    print(args.irri_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
