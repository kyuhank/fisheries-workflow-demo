# Hosted public-data run evidence, 13 October 2026

These four run bundles are unchanged copies of the public hosted runs of the paper demo at source commit `90e59f98d3f20006127aa44c686b0ae6d3e0258d`. Their source manifests, recorded inputs, code, settings, records, numerical outputs and reports remain inside each ZIP. `acceptance.json` and `github-independent-verification.json` are unchanged verification records from the same check. `MANIFEST.json` records run identities and original bundle hashes; `SHA256SUMS.json` checks every delivered file.

| Case | Executed jobs | Retained jobs | Recorded execution |
| --- | ---: | ---: | --- |
| 01-full2021 | 22 | 0 | [GitHub run 38326908624](https://github.com/kyuhank/fisheries-workflow-demo/actions/runs/38326908624) |
| 02-update2022 | 22 | 0 | [GitHub run 38327224611](https://github.com/kyuhank/fisheries-workflow-demo/actions/runs/38327224611) |
| 03-growth035 | 10 | 12 | [GitHub run 38327486257](https://github.com/kyuhank/fisheries-workflow-demo/actions/runs/38327486257) |
| 04-buffer060 | 3 | 19 | [GitHub run 38327738192](https://github.com/kyuhank/fisheries-workflow-demo/actions/runs/38327738192) |

The growth update changes growth to 0.35; the final management update changes the buffered-rule setting to 0.60. The hosted check verifies execution, producing run identity, selective retention, fixed-support CPUE calculations, rendered reports and artifact/checkpoint custody. It does not repeat the native bundle reproduction or compare these hosted selective updates with new full executions. Earlier local equivalence and reconstruction checks are separate evidence. These records do not establish scientific validity of the illustrative CPUE, assessment or MSE.

The original bundles have 273 members, with 271 entries in their original `SHA256SUMS.json`; `REPRODUCE.txt` and the manifest itself are not included in that original internal manifest. All original declared hashes and ZIP CRCs were checked; the external bundle hash here covers the entire unchanged ZIP. Download and keep the files if needed. Fixed byte hashes identify these copies; GitHub/GitHub Pages availability and the continued operation of free hosted services are not a durable repository guarantee.

## Public sources, units and conditions

WCPFC/SPC longline catch and effort: [public download page](https://www.wcpfc.int/index.php/sustainability/scientific-data/wcpfc-public-domain-aggregated-catcheffort-data-download-page), [April 2026 source ZIP](https://www.wcpfc.int/sites/default/files/2026-04/WCPFC_L_PUBLIC_BY_YY_QTR_FLAG.zip). Annual catch: [February 2026 yearbook source ZIP](https://www.wcpfc.int/sites/default/files/2026-03/YB_WCPFC_2026-02-25.zip). Source archives, their hashes and notices are preserved in the bundles and in [the source-data guide](https://github.com/kyuhank/fisheries-workflow-demo/blob/90e59f98d3f20006127aa44c686b0ae6d3e0258d/data/public/README.md).

The observations are released fleet–quarter–5-degree-cell aggregates; row IDs identify original CSV rows, rather than vessels or fishing sets. `HHOOKS` is hundreds of hooks, converted to hooks by multiplying by 100; `ALB_N` is numbers of albacore. The CPUE model predicts at 1,000 hooks in six common Fiji strata, averages equally and divides by the first year’s prediction. This relative index is dimensionless. The baseline uses 132 rows through 2021; the update uses 138 rows through 2022. Cells with fewer than three vessels are masked as zero and blank fleet codes mark confidential cells; these are excluded rather than treated as observed zero catches. These selected rows have positive albacore counts. The independent South Pacific catch series covers all gears and fleets in metric tonnes, with discards included only from 2017. Public aggregation omits vessel/targeting information; the small fleet index and teaching models are not a validated stock assessment.

Retain WCPFC/SPC attribution and all source notices. The repository’s MIT licence applies to its code and documentation and does not relicense these statistical data. Each bundle preserves its `LICENSE`, `THIRD_PARTY.md` and component notices. No private session credentials or private capability files are included in this delivery.
