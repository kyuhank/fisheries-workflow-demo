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
  fig-height: 3.2
---

<style>
body { max-width: 880px; margin: 24px auto; padding: 0 20px; font: 16px/1.45 system-ui, sans-serif; color: #243649; }
h1 { font-size: 27px; line-height: 1.2; }
h2 { font-size: 20px; margin-top: 20px; }
a { color: #1779a0; overflow-wrap: anywhere; }
img, svg { max-width: 100%; height: auto; }
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th, td { padding: 6px; border-bottom: 1px solid #dde5eb; text-align: left; }
.cell-output-display { overflow-x: auto; }
</style>

# Management trial inputs



|Case          |First future year |Starting B/K |Reference catch (t/y) |
|:-------------|:-----------------|:------------|:---------------------|
|Assessment A1 |2022              |0.4952       |73590                 |
|Assessment A2 |2022              |0.4909       |73590                 |
|Assessment B1 |2022              |0.4774       |73590                 |
|Assessment B2 |2022              |0.474        |73590                 |




|Future years |Trials/case/scenario |Growth CV |Observation CV |
|:------------|:--------------------|:---------|:--------------|
|15           |20                   |0.2       |0.15           |


Start after the final historical catch. Rules share saved scenarios and paired errors. Realised catch is capped at 40% of true starting biomass. Fixed fitted cases and toy errors define conditional demonstrations.

**Scope:** selected Fiji fleet index with stock-wide catches is a teaching assumption; the index is not validated as stock-wide abundance.

---

Run `001`. [Data & full record](report-data.json) · [Code 7ae67f11](https://github.com/kyuhank/fisheries-workflow-mse-demo/commit/7ae67f11217ef10ba8f4fb3a52707707377c1f32) · [Workflow 9cb9e72e](https://github.com/kyuhank/fisheries-workflow-demo/commit/9cb9e72ec890e86e1f268a23d829e7c2ab8bde93) · Image 9dea950a713b.

Data: WCPFC/SPC public statistics. [Source 1](https://www.wcpfc.int/sites/default/files/2026-04/WCPFC_L_PUBLIC_BY_YY_QTR_FLAG.zip) · [Source 2](https://www.wcpfc.int/sites/default/files/2026-03/YB_WCPFC_2026-02-25.zip).
