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

# Assessment inputs B

22 annual index/catch pairs, 2000–2021.



<table>
 <thead>
  <tr>
   <th style="text-align:left;"> Year </th>
   <th style="text-align:left;"> Relative CPUE </th>
   <th style="text-align:left;"> Removals (t) </th>
  </tr>
 </thead>
<tbody>
  <tr>
   <td style="text-align:left;"> 2000 </td>
   <td style="text-align:left;"> 1 </td>
   <td style="text-align:left;"> 49980 </td>
  </tr>
  <tr>
   <td style="text-align:left;"> 2001 </td>
   <td style="text-align:left;"> 0.8702 </td>
   <td style="text-align:left;"> 65640 </td>
  </tr>
  <tr>
   <td style="text-align:left;"> 2020 </td>
   <td style="text-align:left;"> 0.4307 </td>
   <td style="text-align:left;"> 72600 </td>
  </tr>
  <tr>
   <td style="text-align:left;"> 2021 </td>
   <td style="text-align:left;"> 0.6146 </td>
   <td style="text-align:left;"> 70330 </td>
  </tr>
</tbody>
</table>


Joined by year. First and last two rows shown; complete input pairs are in Data.

**Scope:** selected Fiji fleet index with stock-wide catches is a teaching assumption; the index is not validated as stock-wide abundance.

---

Run `001`. [Data & full record](report-data.json) · [Code 0b707160](https://github.com/kyuhank/fisheries-workflow-assessment-demo/commit/0b7071600b636b17edacd00ed216af2aff19090a) · [Workflow 9cb9e72e](https://github.com/kyuhank/fisheries-workflow-demo/commit/9cb9e72ec890e86e1f268a23d829e7c2ab8bde93) · Image 9dea950a713b.

Data: WCPFC/SPC public statistics. [Source 1](https://www.wcpfc.int/sites/default/files/2026-04/WCPFC_L_PUBLIC_BY_YY_QTR_FLAG.zip) · [Source 2](https://www.wcpfc.int/sites/default/files/2026-03/YB_WCPFC_2026-02-25.zip).
