# Reproduction checks — 1.12.0

The reader source is `1610b37`; saved calculations were produced by `9cb9e72`.
The component pins and PDF hashes are in [validation.json](validation.json).

| Check | Observed result |
| --- | --- |
| Component Make commands | CPUE, assessment and MSE preparation completed in their assigned containers. |
| Complete workflow | All 22 jobs and native Quarto PDFs completed in 113.35 s. Every PDF is one page. |
| Archived workflow | All 22 numerical outputs reproduced without external networking in 116.082 s. |
| Local browser | Three manual handovers, automatic connection, growth and buffer updates, a 2022 snapshot and a single-job run completed. Retained producing records were unchanged. |
| Downloaded 2022 run | All 22 numerical outputs reproduced offline in 103.015 s. |
| Preserved software | The image archive and 24 host-package sources were checked; those package sources were installed offline into a new library. |
| Earlier image-binding check (`f81fdc6`) | Two actual image configurations selected 3, 9 or 14 jobs. Retained records/artifacts and all numerical outputs remained unchanged. Only image metadata changed; installed packages were identical. |
| Free-service request limit | The final serialized completion payload was 15,331,329 bytes, below 16,000,000. This measurement used an HTTP double. |

These warm local timings used two coordinator CPUs and 4 GiB, with each job
container limited to one CPU and 2 GiB. They exclude image download and GitHub
queue time. Local browser and reproduction checks used a loopback-only network
namespace; an external request failed. Numerical comparison follows the saved
`comparison-policy.json` (relative `1e-8`, absolute `1e-9`, with recorded diagnostic
exceptions). These are execution checks for an illustrative workflow.

The earlier oversized completion payload and the initial local query-parser
failure were retained in the development evidence; both were corrected before
this release. The recorded artifacts and original producing identities were
preserved during reader updates.

To repeat or prepare independent storage, use the release's `OFFLINE.md` and
`make reproduce`. `make portable` preserves the separate images and host package
sources; R, a suitable compiler, Make and Docker are prerequisites.
