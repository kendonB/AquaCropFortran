#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np


@dataclass(frozen=True)
class PrmDaySeries:
    dates: list[dt.date]
    cc_pct: np.ndarray
    biomass_cum_tonha: np.ndarray


def read_prmday(path: Path) -> PrmDaySeries:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()

    header_i = None
    for i, line in enumerate(lines):
        if re.match(r"\s*Day\s+Month\s+Year\b", line):
            header_i = i
            break
    if header_i is None:
        raise ValueError(f"{path}: could not find PRMday header line starting with 'Day Month Year'")

    cols = lines[header_i].split()
    want = ["Day", "Month", "Year", "CC", "Biomass"]
    missing = [c for c in want if c not in cols]
    if missing:
        raise ValueError(f"{path}: missing expected columns: {missing}")

    col_idx = {c: cols.index(c) for c in want}

    dates: list[dt.date] = []
    cc: list[float] = []
    biomass: list[float] = []

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
            cc.append(float(parts[col_idx["CC"]]))
            biomass.append(float(parts[col_idx["Biomass"]]))
        except Exception:  # noqa: BLE001
            continue

    if not dates:
        raise ValueError(f"{path}: no data rows parsed")

    return PrmDaySeries(
        dates=dates,
        cc_pct=np.asarray(cc, dtype=float),
        biomass_cum_tonha=np.asarray(biomass, dtype=float),
    )


def detect_cut_indices(cc_pct: np.ndarray, cut_threshold_pct: float) -> np.ndarray:
    if len(cc_pct) < 2:
        return np.array([], dtype=int)
    drops = cc_pct[:-1] - cc_pct[1:]
    return np.where(drops > cut_threshold_pct)[0]


def read_harvest_cut_dates(path: Path) -> list[dt.date]:
    """
    Parse AquaCrop PRMharvests.OUT and return the list of cut dates.

    PRMharvests reports cut dates on the day the harvest is recorded, while PRMday reflects the
    post-cut canopy state on the following day. For building a daily 'biomass since cut' series
    from PRMday cumulative Biomass, we reset on (cut_date + 1 day).
    """
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    header_i = None
    for i, line in enumerate(lines):
        if re.match(r"\s*Nr\s+Day\s+Month\s+Year\b", line):
            header_i = i
            break
    if header_i is None:
        raise ValueError(f"{path}: could not find PRMharvests header line starting with 'Nr Day Month Year'")

    dates: list[dt.date] = []
    for line in lines[header_i + 2 :]:
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        try:
            nr = int(parts[0])
        except Exception:  # noqa: BLE001
            continue
        if nr in {0, 9999}:
            continue
        try:
            day = int(parts[1])
            month = int(parts[2])
            year = int(parts[3])
            dates.append(dt.date(year, month, day))
        except Exception:  # noqa: BLE001
            continue

    if not dates:
        raise ValueError(f"{path}: no cut dates parsed")
    return dates


def per_cut_yield_kgdmha(biomass_cum_tonha: np.ndarray, cut_idx: np.ndarray) -> np.ndarray:
    """Yield harvested at each cut, in kg DM/ha, derived from PRMday cumulative Biomass (ton/ha)."""
    yields: list[float] = []
    prev_cut_biomass = 0.0
    for idx in cut_idx:
        this_cut_biomass = float(biomass_cum_tonha[idx])
        y_tonha = this_cut_biomass - prev_cut_biomass
        yields.append(y_tonha * 1000.0)
        prev_cut_biomass = this_cut_biomass
    return np.asarray(yields, dtype=float)


def biomass_since_last_cut_kgdmha(
    biomass_cum_tonha: np.ndarray,
    reset_idx: np.ndarray,
) -> np.ndarray:
    """
    Biomass produced since the last cut (kg DM/ha), derived from PRMday cumulative Biomass (ton/ha).

    For PRMday output, cuts typically apply between the reported harvest day and the next day. Therefore
    reset indices should usually correspond to the day AFTER each cut date.
    """
    out = np.zeros_like(biomass_cum_tonha, dtype=float)
    baseline = 0.0
    reset_set = set(int(i) for i in reset_idx.tolist())
    for i, b in enumerate(biomass_cum_tonha):
        out[i] = (float(b) - baseline) * 1000.0
        if i in reset_set:
            baseline = float(b)
    return out


def cover_from_prmday_and_cc(
    cc_pct: np.ndarray,
    biomass_cum_tonha: np.ndarray,
    cut_idx: np.ndarray,
    mode: str,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Build a 'standing pasture cover' proxy in kg DM/ha.

    For each cut, we compute:
      yield_kgDM/ha = Δ(PRMday Biomass at cut) * 1000
      ΔCC = CC_pre - CC_post
      k_i = yield_kgDM/ha / ΔCC  [kgDM/ha per 1% CC]

    Then:
      - mode='median': cover = median(k_i) * CC
      - mode='piecewise': use the segment's k_i between cuts

    Returns (cover_kgdmha, k_by_cut).
    """
    if len(cut_idx) == 0:
        raise ValueError("No cuts detected (try lowering --cut-threshold)")

    yields_kg = per_cut_yield_kgdmha(biomass_cum_tonha, cut_idx)
    dcc = cc_pct[cut_idx] - cc_pct[cut_idx + 1]
    with np.errstate(divide="ignore", invalid="ignore"):
        k = yields_kg / dcc
    k = k.astype(float)

    finite_k = k[np.isfinite(k) & (k > 0)]
    if finite_k.size == 0:
        raise ValueError("Could not compute any finite k values from cuts")

    k_median = float(np.median(finite_k))

    if mode == "median":
        return k_median * cc_pct, k

    if mode == "piecewise":
        cover = np.full_like(cc_pct, np.nan, dtype=float)
        start = 0
        last_k = k_median
        for ki, idx in zip(k, cut_idx, strict=True):
            if np.isfinite(ki) and ki > 0:
                last_k = float(ki)
                cover[start : idx + 1] = last_k * cc_pct[start : idx + 1]
            start = idx + 1
        cover[start:] = last_k * cc_pct[start:]
        return cover, k

    raise ValueError(f"Unknown mode: {mode!r}")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Plot pasture-cover style series in kg DM/ha from AquaCrop PRMday output.\n\n"
            "Note: PRMday 'Biomass' (ton/ha) is cumulative across cuttings, so a literal pasture cover "
            "time series must be derived (e.g., residual cover + biomass since last cut)."
        )
    )
    ap.add_argument(
        "--prmday",
        type=Path,
        default=None,
        help="Path to *PRMday.OUT (default: first match in OUTP/*PRMday.OUT in current dir)",
    )
    ap.add_argument("--out", type=Path, default=Path("pasture_cover_kgDMha.png"))
    ap.add_argument(
        "--harvests",
        type=Path,
        default=None,
        help="Path to *PRMharvests.OUT (default: first match in OUTP/*PRMharvests.OUT in current dir)",
    )
    ap.add_argument(
        "--mode",
        choices=["median", "piecewise"],
        default="median",
        help="How to map CC to kg DM/ha (default: median).",
    )
    ap.add_argument(
        "--kind",
        choices=["pasture_cover", "biomass_since_cut", "both", "cover_proxy", "cover"],
        default="pasture_cover",
        help=(
            "What to plot. 'pasture_cover' is residual + biomass since last cut (recommended). "
            "'cover_proxy' (alias: 'cover') maps CC%% to kg DM/ha using cut-induced CC drops (heuristic). "
            "'both' plots pasture_cover (top) and biomass_since_cut (bottom)."
        ),
    )
    ap.add_argument(
        "--residual-kgdmha",
        type=float,
        default=1500.0,
        help="Residual (post-grazing) pasture cover for pasture_cover plots (default: 1500).",
    )
    ap.add_argument(
        "--target-kgdmha",
        type=float,
        default=1500.0,
        help="Target harvested biomass since last cut, for reference line when plotting biomass_since_cut (default: 1500).",
    )
    ap.add_argument(
        "--cut-threshold",
        type=float,
        default=10.0,
        help="Detect cuts when CC drops by more than this many percentage points (default: 10).",
    )
    ap.add_argument(
        "--mark-cuts",
        action="store_true",
        help="Draw vertical lines at cut dates.",
    )
    args = ap.parse_args(argv)

    prmday = args.prmday
    if prmday is None:
        matches = sorted(Path("OUTP").glob("*PRMday.OUT"))
        if not matches:
            raise SystemExit("No --prmday provided and no OUTP/*PRMday.OUT found in current dir")
        prmday = matches[0]

    harvests = args.harvests
    if harvests is None:
        matches = sorted(Path("OUTP").glob("*PRMharvests.OUT"))
        harvests = matches[0] if matches else None

    s = read_prmday(prmday)
    date_to_idx = {d: i for i, d in enumerate(s.dates)}

    cut_dates: list[dt.date] | None = None
    reset_idx = None
    if harvests is not None:
        cut_dates = read_harvest_cut_dates(harvests)
        reset_dates = [d + dt.timedelta(days=1) for d in cut_dates]
        reset_idx = np.asarray([date_to_idx[d] for d in reset_dates if d in date_to_idx], dtype=int)
    else:
        # Fallback: infer cuts from CC drops (can miss cuts when CC is already near CCcut).
        cut_idx = detect_cut_indices(s.cc_pct, cut_threshold_pct=args.cut_threshold)
        reset_idx = np.asarray([i + 1 for i in cut_idx], dtype=int)
        cut_dates = [s.dates[i] for i in cut_idx.tolist()]

    biomass_since = biomass_since_last_cut_kgdmha(s.biomass_cum_tonha, reset_idx=reset_idx)
    pasture_cover = args.residual_kgdmha + biomass_since
    n_resets = int(len(reset_idx))
    kind = "cover_proxy" if args.kind == "cover" else args.kind

    x = [dt.datetime(d.year, d.month, d.day) for d in s.dates]

    if kind == "cover_proxy":
        cc_drop_cut_idx = detect_cut_indices(s.cc_pct, cut_threshold_pct=args.cut_threshold)
        cover, k_by_cut = cover_from_prmday_and_cc(
            s.cc_pct, s.biomass_cum_tonha, cut_idx=cc_drop_cut_idx, mode=args.mode
        )
        finite_k = k_by_cut[np.isfinite(k_by_cut) & (k_by_cut > 0)]
        k_median = float(np.median(finite_k))

        plt.figure(figsize=(14, 5))
        plt.plot(x, cover, lw=2)
        plt.title(
            "Pasture cover proxy (kg DM/ha; CC mapped to biomass via cut-induced CC drops)\n"
            f"mode={args.mode}, cc-drop-cuts={len(cc_drop_cut_idx)}, resets={n_resets}, "
            f"k_median={k_median:.1f} kg DM/ha per 1% CC"
        )
        plt.ylabel("Cover proxy (kg DM/ha)")
        plt.xlabel("Date")
        plt.grid(True, alpha=0.25)
        if args.mark_cuts:
            for idx in reset_idx:
                plt.axvline(x[idx], color="k", alpha=0.05, lw=1)

    elif kind == "pasture_cover":
        plt.figure(figsize=(14, 5))
        plt.plot(x, pasture_cover, lw=2)
        plt.axhline(args.residual_kgdmha, color="k", alpha=0.25, lw=1)
        plt.axhline(args.residual_kgdmha + args.target_kgdmha, color="k", alpha=0.4, lw=1)
        plt.title(
            "Pasture cover (kg DM/ha) = residual + biomass since last cut\n"
            f"resets={n_resets}, residual={args.residual_kgdmha:.0f}, target={args.target_kgdmha:.0f}"
        )
        plt.ylabel("Pasture cover (kg DM/ha)")
        plt.xlabel("Date")
        plt.grid(True, alpha=0.25)
        if args.mark_cuts:
            for idx in reset_idx:
                plt.axvline(x[idx], color="k", alpha=0.05, lw=1)

    elif kind == "biomass_since_cut":
        plt.figure(figsize=(14, 5))
        plt.plot(x, biomass_since, lw=2)
        plt.axhline(args.target_kgdmha, color="k", alpha=0.4, lw=1)
        plt.title(
            "Biomass produced since last cut (kg DM/ha)\n"
            f"resets={n_resets}, target={args.target_kgdmha:.0f} kg DM/ha"
        )
        plt.ylabel("Biomass since last cut (kg DM/ha)")
        plt.xlabel("Date")
        plt.grid(True, alpha=0.25)
        if args.mark_cuts:
            for idx in reset_idx:
                plt.axvline(x[idx], color="k", alpha=0.05, lw=1)

    else:  # both
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 7), sharex=True)
        ax1.plot(x, pasture_cover, lw=2)
        ax1.axhline(args.residual_kgdmha, color="k", alpha=0.25, lw=1)
        ax1.axhline(args.residual_kgdmha + args.target_kgdmha, color="k", alpha=0.4, lw=1)
        ax1.set_title(
            "Pasture cover (top) and biomass since last cut (bottom)\n"
            f"resets={n_resets}, residual={args.residual_kgdmha:.0f}, target={args.target_kgdmha:.0f}"
        )
        ax1.set_ylabel("Pasture cover (kg DM/ha)")
        ax1.grid(True, alpha=0.25)

        ax2.plot(x, biomass_since, lw=2)
        ax2.axhline(args.target_kgdmha, color="k", alpha=0.4, lw=1)
        ax2.set_ylabel("Biomass since cut (kg DM/ha)")
        ax2.set_xlabel("Date")
        ax2.grid(True, alpha=0.25)

        if args.mark_cuts:
            for idx in reset_idx:
                ax1.axvline(x[idx], color="k", alpha=0.05, lw=1)
                ax2.axvline(x[idx], color="k", alpha=0.05, lw=1)

        fig.tight_layout()

    plt.tight_layout()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(args.out, dpi=150)
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
