---
lang: en-NZ
keep-md: true
format:
  html:
    minimal: true
    embed-resources: true
    fig-format: svg
    toc: false
    theme: none
  typst:
    papersize: a4
    margin:
      x: 15mm
      y: 15mm
    fontsize: 10pt
    fig-format: svg
    keep-typ: true
    toc: false
execute:
  echo: false
  warning: false
  message: false
  fig-width: 8
  fig-height: 2.9
---

<style>
body { max-width: 880px; margin: 28px auto; padding: 0 22px; font: 15px/1.4 system-ui, sans-serif; color: #243649; }
h1 { font-size: 26px; font-weight: 600; line-height: 1.2; margin: 0 0 10px; }
h2 { font-size: 19px; margin: 20px 0 10px; }
p { margin: 10px 0; }
a { color: #17688a; overflow-wrap: anywhere; }
img, svg { max-width: 100%; height: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; margin: 12px 0 16px; }
th, td { padding: 6px 8px; border-bottom: 1px solid #dce3e8; text-align: left; vertical-align: top; }
th { font-weight: 600; color: #243649; }
hr { border: 0; border-top: 1px solid #dce3e8; margin-top: 20px; }
.cell-output-display { overflow-x: auto; }
@media (max-width: 600px) { body { margin: 16px auto; padding: 0 14px; } th, td { padding: 5px; } }
</style>

# CPUE analysis B

**CPUE analyst** · Run 001 · Years 2000–2021

Calculation finished (container exit 0).

![](report_files/figure-typst/unnamed-chunk-1-1.svg)

|Analysis |Rows |Excluded |Converged |Dispersion |Score residual |Final index |
|:--------|:----|:--------|:---------|:----------|:--------------|:-----------|
|B        |132  |0        |Yes       |3011       |1.332e-15      |0.6146      |


Quasipoisson GLM: year + quarter. Nominal = 1,000 × annual fish / annual hooks; both curves use the same selected records. Arithmetic mean of response-scale predictions with equal fixed stratum weights. The relative index passed to assessment equals one in its first year.

**Scope:** Fiji fleet; six observed cell–quarter strata, 2000–2021; aggregate records without vessel effects or confidence intervals.

**Inputs used**


|Input        |Analyst      |Produced in |
|:------------|:------------|:-----------|
|Extract data |Data analyst |Run 001     |


---

Saved files: `report-data.json` · `record.json` · [Code 7d17fc59](https://github.com/kyuhank/fisheries-workflow-cpue-demo/commit/7d17fc5962466cdabc27d17e004bed87136b38bc) · [Workflow 2a8dc292](https://github.com/kyuhank/fisheries-workflow-demo/commit/2a8dc292696fa42866b1f28139c23510dc75f140) · Image 9dea950a713b.

Data: WCPFC/SPC public statistics. [Source 1](https://www.wcpfc.int/sites/default/files/2026-04/WCPFC_L_PUBLIC_BY_YY_QTR_FLAG.zip) · [Source 2](https://www.wcpfc.int/sites/default/files/2026-03/YB_WCPFC_2026-02-25.zip).
