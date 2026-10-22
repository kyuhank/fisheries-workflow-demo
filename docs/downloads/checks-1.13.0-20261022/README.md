# Version 1.13.0 checks

Local, offline and hosted execution checks passed. The final browser CI check is pending.

| Check | Result |
| --- | --- |
| Complete local workflow | 22 jobs and Quarto PDFs; 105.408 s with cached images |
| Offline `make reproduce` | All 22 numerical outputs agree; 118.079 s with no external network |
| Job PDFs | One page each; producing analyst, run and incoming result links checked |
| Runtime preparation | Three environment inventories; separate calculation and rendering containers for every job |
| Standalone archive | All 22 saved PDFs, Data/Inputs & versions tabs and downloads checked |
| Status layout | Text stays inside cards and clears View at desktop/mobile widths and 125% zoom |
| Input transfer | 16 local service fixtures cover manual transfer, Connect, updates and interrupted requests |

Inspect a job PDF: [CPUE](../../example/cpue_report/report.pdf) · [assessment](../../example/assessment_report/report.pdf) · [MSE](../../example/mse_report/report.pdf).

[Download the archive](../fisheries-workflow-offline-1.13.0.zip) · [Exact sources, PDF checksums, numerical tolerances and retained failures](verification.json).

Live checks also passed for the complete workflow, a growth-rate update with manual transfer, and an MSE-buffer update. They verified accepted outputs, PDFs and retained records. [Run details and timings](verification.json) distinguish hosted execution from local reproduction.

Sources: [coordinator](https://github.com/kyuhank/fisheries-workflow-demo/tree/1f3bb8740c5db464656918802f06c83fad67b15b), [producing version](https://github.com/kyuhank/fisheries-workflow-demo/tree/2a8dc292696fa42866b1f28139c23510dc75f140), [CPUE](https://github.com/kyuhank/fisheries-workflow-cpue-demo/tree/7d17fc5962466cdabc27d17e004bed87136b38bc), [assessment](https://github.com/kyuhank/fisheries-workflow-assessment-demo/tree/50412b29afff933601eb2c04ffa56b71702538ac), [MSE](https://github.com/kyuhank/fisheries-workflow-mse-demo/tree/bfd7066a5b7fad6bc302bf311d63b20e32dfa9a4).

The archive preserves the producing calculation records and includes the corrected QC card layout. Packaging removes duplicated interface HTML while retaining the canonical reports, data and records. Local reproduction requires prepared R/Make/Docker dependencies and the recorded image. A fresh OS or image import was not tested. Timings exclude GitHub scheduling and image downloads.

The [previous version's checks](../checks-1.12.0-20261022/README.md) remain available.
