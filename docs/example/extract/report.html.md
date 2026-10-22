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

# Extracted data



<table>
 <thead>
  <tr>
   <th style="text-align:left;"> Records </th>
   <th style="text-align:left;"> Years </th>
   <th style="text-align:left;"> Fleets </th>
   <th style="text-align:left;"> Catch years </th>
  </tr>
 </thead>
<tbody>
  <tr>
   <td style="text-align:left;"> 132 </td>
   <td style="text-align:left;"> 2000–2021 </td>
   <td style="text-align:left;"> FJ </td>
   <td style="text-align:left;"> 2000–2021 </td>
  </tr>
</tbody>
</table>




<table>
 <thead>
  <tr>
   <th style="text-align:left;"> Year </th>
   <th style="text-align:left;"> Removals (t) </th>
  </tr>
 </thead>
<tbody>
  <tr>
   <td style="text-align:left;"> 2000 </td>
   <td style="text-align:left;"> 49980 </td>
  </tr>
  <tr>
   <td style="text-align:left;"> 2001 </td>
   <td style="text-align:left;"> 65640 </td>
  </tr>
  <tr>
   <td style="text-align:left;"> 2020 </td>
   <td style="text-align:left;"> 72600 </td>
  </tr>
  <tr>
   <td style="text-align:left;"> 2021 </td>
   <td style="text-align:left;"> 70330 </td>
  </tr>
</tbody>
</table>


Selected records → CPUE; annual removals → assessment. First and last two catch rows shown; joins use year.

---

Run `001`. [Data & full record](report-data.json) · [Code d4454fcf](https://github.com/kyuhank/fisheries-workflow-cpue-demo/commit/d4454fcfa9a23bd590344ad92940a13fa0a41c06) · [Workflow 9cb9e72e](https://github.com/kyuhank/fisheries-workflow-demo/commit/9cb9e72ec890e86e1f268a23d829e7c2ab8bde93) · Image 9dea950a713b.

Data: WCPFC/SPC public statistics. [Source 1](https://www.wcpfc.int/sites/default/files/2026-04/WCPFC_L_PUBLIC_BY_YY_QTR_FLAG.zip) · [Source 2](https://www.wcpfc.int/sites/default/files/2026-03/YB_WCPFC_2026-02-25.zip).
