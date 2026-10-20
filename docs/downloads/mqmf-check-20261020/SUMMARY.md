# Check of the MQMF example

The separate three-job example was repeated on 20 October 2026 using its recorded software. The source was mounted read-only; the run used two CPUs and 4 GiB memory, with network access and image pulling disabled. It completed successfully in 3.07 seconds. This is an execution time, with no time-saving comparison.

| Check | Result |
|:--|:--|
| Input mapping | All 72 values in the 24-row example were preserved exactly. |
| Direct and adapter calls | All 24 predictions agreed, with zero numerical difference. |
| Growth setting 0.4 to 0.35 | Two jobs reran; the reference output and producing record were retained. |
| Updated versus fresh calculation | All 24 predictions and 120 comparison values agreed, with zero numerical difference. |
| Declared scale mismatch | The deliberately linear-labelled fixture was rejected before the consumer calculation. Previously accepted results were retained. |

The calculation uses unchanged MQMF 0.1.5 source at f171966258b9dd8d6cdfcc150930cdb45d23cf65 and its supplied abdat example. Both paths call the same function with fixed parameters; no optimisation is performed. The example uses a separately pinned coordinator copy at 819c67034625b9a30b4196fd5ec17b0c74f60ba7, distinct from the current 22-job WCPFC demonstration. CPUE physical units and normalisation are undocumented; values retain their supplied scale. These checks establish technical adaptation and reuse for this calculation, without establishing model validity, human adoption or labour savings.

The original command output is preserved in stdout.json and stderr.txt. The JSON files identify the runtime, inputs, source versions, producing runs and verification results. SHA256SUMS records every selected file. The source, licence notices and repeat instructions are in the [versioned example package](https://kyuhank.github.io/fisheries-workflow-demo/downloads/fisheries-workflow-mqmf-1.10.0.zip).
