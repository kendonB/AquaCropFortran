# Canterbury dairy grass (perennial ryegrass pasture) – AquaCrop Fortran example

This example represents a “typical Canterbury dairy pasture” as a **perennial herbaceous forage crop** with **multiple cuttings** (cuts ≈ rotational grazings).

It is **synthetic** (climate + soil are placeholders) but runs end to end and produces the key outputs needed for pasture calibration:
- Daily canopy cover and aboveground biomass
- Water balance components (rain, irrigation, ET, drainage, etc.)
- Per-cut harvested biomass (harvests output)

## Run

From the repo root:

```bash
cd src && make
cd ../examples/canterbury_dairy_grass
../../src/aquacrop
```

Outputs are written to `OUTP/`:
- `OUTP/CanterburyDairyGrassPRMday.OUT` (daily series)
- `OUTP/CanterburyDairyGrassPRMseason.OUT` (season totals)
- `OUTP/CanterburyDairyGrassPRMharvests.OUT` (per-cut harvested biomass)
- `OUTP/CanterburyDairyGrassPRMirrInfo.OUT` (irrigation events/intervals)

## Plot pasture cover (kg DM/ha)

`PRMday.OUT` reports **cumulative** biomass (ton DM/ha) across multiple cuttings. For a “standing pasture cover” proxy (kg DM/ha), this script uses PRMday Biomass to quantify each cut and uses the CC% drops to shape the daily curve:

```bash
python3 plot_pasture_cover.py --mark-cuts --out pasture_cover_kgDMha.png
```

## What’s configured

- Crop: `DATA/CanterburyRyegrass.CRO` (parameter baseline from Terán‑Chaves et al., 2022, Water, DOI: 10.3390/w14233933)
- Grazing as cuts: `DATA/CanterburyDairyGrass.MAN`
  - Post-cut canopy cover set to **40%** (`CCcut = 40`)
  - Generated cuts by **biomass since last cut** (criterion `DryB`) with a target of **1.5 t DM/ha per cut**
- Irrigation: `DATA/CanterburyPivot.IRR`
  - Generated irrigation when **80% of RAW** is depleted (`AllRAW`, target = 80)
  - Fixed application depth **20 mm** per event
- Soil templates:
  - `DATA/CanterburySiltLoam.SOL` (used by default in the project file)
  - `DATA/CanterburyStony.SOL` (alternative template; adjust gravel/FC/WP/Ksat for a stony Canterbury soil)

## Swap in real Canterbury climate (NIWA / station)

Replace the synthetic daily climate files in `DATA/`:
- `*.Tnx` (daily Tmin/Tmax)
- `*.ETo` (daily reference ET0)
- `*.PLU` (daily rainfall)

Then run the validator:

```bash
python3 validate_climate.py DATA/YourSite.Tnx DATA/YourSite.ETo DATA/YourSite.PLU
```
