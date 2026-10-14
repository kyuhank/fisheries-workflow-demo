# CPUE analysis A

Fiji longline albacore · 2000--2021 · 132 released fleet--cell--quarter records.

![](report-plot-01.svg){fig-alt="Fish per 1,000 hooks"}

Fish per 1,000 hooks

Both curves use the same selected rows; 132 used, 0 excluded; no additional effort filter.

Nominal CPUE = 1,000 × annual fish numbers / annual hooks.

Standardised A holds cell--quarter composition fixed: predict catch at 1,000 hooks in each of the six strata, then average with equal weights.

Quasipoisson GLM: year + cell--quarter stratum · Arithmetic mean of response-scale predictions with equal fixed stratum weights.

These released strata cover the selected fleet. No confidence intervals or stock-wide abundance validation are supplied.

  Year   Standardised (fish/1,000 hooks)   Nominal (fish/1,000 hooks)
  ------ --------------------------------- ----------------------------
  2000   18.62                             16.08
  2021   10.47                             9.802
