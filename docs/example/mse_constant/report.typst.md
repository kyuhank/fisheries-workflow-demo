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

# Constant catch

**MSE analyst** · Run 001 · Years 2022–2036

Calculation finished (container exit 0).

Keep catch at its recent mean. 

![](report_files/figure-typst/unnamed-chunk-1-1.svg)

|Rule           |Mean catch (t/y) |Final B/K |Below 0.2 (%) |Catch change (%) |Capped trials |
|:--------------|:----------------|:---------|:-------------|:----------------|:-------------|
|Constant catch |69870            |0.1548    |57.5          |1.769            |79            |


Final B/K is the trial median; below-threshold counts trials with any low-biomass year. Catch change includes the first change from reference catch. Capped trials had requested catch above the biomass guardrail.

160 trials per rule; 15 future years; 4 fitted cases; 2 growth scenarios. All rules use the same saved errors and cases, with equal case/scenario weights. Realised catch is capped at 40% of starting biomass. Dotted line: B/K = 0.2. 

**Scope:** these illustrative trials use simplified fitted cases and errors; trial fractions are not calibrated management risks.

**Inputs used**


|Input       |Analyst     |Produced in |
|:-----------|:-----------|:-----------|
|Prepare MSE |MSE analyst |Run 001     |


---

Saved files: `report-data.json` · `record.json` · [Code bfd7066a](https://github.com/kyuhank/fisheries-workflow-mse-demo/commit/bfd7066a5b7fad6bc302bf311d63b20e32dfa9a4) · [Workflow 2a8dc292](https://github.com/kyuhank/fisheries-workflow-demo/commit/2a8dc292696fa42866b1f28139c23510dc75f140) · Image 9dea950a713b.

Data: WCPFC/SPC public statistics. [Source 1](https://www.wcpfc.int/sites/default/files/2026-04/WCPFC_L_PUBLIC_BY_YY_QTR_FLAG.zip) · [Source 2](https://www.wcpfc.int/sites/default/files/2026-03/YB_WCPFC_2026-02-25.zip).
