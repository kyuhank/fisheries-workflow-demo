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

# Compare assessments

**Assessment analyst** · Run 001 · Years 2000–2021

Calculation finished (container exit 0).

![](report_files/figure-typst/unnamed-chunk-1-1.svg)

|Case          |Fixed r (/y) |Capacity K (t) |Final B/K |Numerical checks |
|:-------------|:------------|:--------------|:---------|:----------------|
|Assessment A1 |0.25         |1029000        |0.5011    |Pass             |
|Assessment A2 |0.3          |890200         |0.4949    |Pass             |
|Assessment B1 |0.25         |1012000        |0.4845    |Pass             |
|Assessment B2 |0.3          |877700         |0.4792    |Pass             |


B/K uses each case's carrying capacity. Fitted parameters and next-year biomass pass to management trial preparation.

**Scope:** selected-fleet CPUE and stock-wide catches are combined only to illustrate the workflow.

**Inputs used**


|Input         |Analyst            |Produced in |
|:-------------|:------------------|:-----------|
|Assessment A1 |Assessment analyst |Run 001     |
|Assessment A2 |Assessment analyst |Run 001     |
|Assessment B1 |Assessment analyst |Run 001     |
|Assessment B2 |Assessment analyst |Run 001     |


---

Saved files: `report-data.json` · `record.json` · [Code 50412b29](https://github.com/kyuhank/fisheries-workflow-assessment-demo/commit/50412b29afff933601eb2c04ffa56b71702538ac) · [Workflow 2a8dc292](https://github.com/kyuhank/fisheries-workflow-demo/commit/2a8dc292696fa42866b1f28139c23510dc75f140) · Image 9dea950a713b.

Data: WCPFC/SPC public statistics. [Source 1](https://www.wcpfc.int/sites/default/files/2026-04/WCPFC_L_PUBLIC_BY_YY_QTR_FLAG.zip) · [Source 2](https://www.wcpfc.int/sites/default/files/2026-03/YB_WCPFC_2026-02-25.zip).
