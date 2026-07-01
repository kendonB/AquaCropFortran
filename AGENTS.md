<INSTRUCTIONS>
Never ever ever run a sudo command. Always ask the user to run these.

Never git commit or git push without the user asking for it or approving it *in their most recent message*.

Pasture plotting rule (Canterbury example):
- Do NOT convert AquaCrop `CC` (canopy cover %) directly into "pasture cover" (kg DM/ha). CC is not biomass and the mapping is not unique.
- In `OUTP/*PRMday.OUT`, the `Biomass` column is cumulative across multiple cuttings; use it to derive `biomass_since_last_cut`.
- For correct reset timing, prefer cut dates from `OUTP/*PRMharvests.OUT` and reset `biomass_since_last_cut` on the day AFTER each cut date (PRMday reflects the post-cut state on the following day).
- For a literal pasture cover series, plot `pasture_cover = residual_kgDMha + biomass_since_last_cut_kgDMha` (residual is an explicit assumption).
- Any `CC`→kgDM/ha curve must be labeled as a proxy and requires calibration/validation.
</INSTRUCTIONS>
