# Public albacore data

The example uses two WCPFC/SPC statistical releases. The Fiji records are a
subset of the international longline release, rather than a separate Fiji dataset.

| Source | Public location | Use |
| --- | --- | --- |
| Longline catch and effort, year/quarter/flag/5° cell | [Download page](https://www.wcpfc.int/index.php/sustainability/scientific-data/wcpfc-public-domain-aggregated-catcheffort-data-download-page), [April 2026 ZIP](https://www.wcpfc.int/sites/default/files/2026-04/WCPFC_L_PUBLIC_BY_YY_QTR_FLAG.zip) | Fiji fleet records, 2000–2022 |
| Yearbook raw data | [February 2026 ZIP](https://www.wcpfc.int/sites/default/files/2026-03/YB_WCPFC_2026-02-25.zip) | South Pacific albacore annual nominal catch, all gears and fleets |
| Longline field definitions | `Longline.pdf` inside the longline ZIP, [preserved copy](Longline.pdf) | Units and confidentiality rules |

The archives are preserved here unchanged. [public-data.json](../public-data.json)
records their hashes, CSV member hashes and preparation code. WCPFC/SPC source
notices and attribution apply; the repository's MIT licence does not relicense
these data.

## From the release to the analysis

`python3 scripts/import-public-data.py` verifies the archives and extracts 662
released Fiji fleet records with positive effort. `HHOOKS` is hundreds of hooks;
the adapter multiplies it by 100. `ALB_N` counts fish. `set_id` identifies an
original CSV row; it does not identify a fishing set or vessel.

[The SQL query](../../workflow/extract-public.sql) selects six cell–quarter strata
observed in every year. The baseline has 132 records through 2021; adding 2022
gives 138. The standardisation predicts each year at 1,000 hooks in the same six
strata, averages them equally and divides by the first year's prediction.

Cells with fewer than three vessels have catch and effort masked as zero.
Blank fleet codes indicate confidential cells. These are excluded before the
Fiji projection; masked zeros are not interpreted as observed zero catches.
The selected 138 records happen to have positive albacore counts. Model tests
check zero catches separately using labelled fixtures.

Annual catch comes from `XLS_SouthPacific_2026-02-25.csv`, summing `ALB` across
all gears and fleets. It is not the catch in the six sampled strata. These nominal
totals include discards only from 2017. Recent eastern Pacific reporting remains
unresolved, so the example ends in 2022. The small fleet CPUE and simplified
assessment/MSE illustrate the workflow; they are not a validated stock assessment.
