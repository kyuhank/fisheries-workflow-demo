# Completion acknowledgement check

An earlier 20 October check saved its final buffer results and both archives, but GitHub run [39365433531](https://github.com/kyuhank/fisheries-workflow-demo/actions/runs/39365433531) ended unsuccessfully after a database response timed out. The original operation receipt and archive hashes confirmed that saving had completed. The failed workflow remains recorded as failed.

Coordinator `379c2bac1cfd1ea8192056f5037100dac1a82e61` checks the authenticated receipt for the original request and operation before resending a large completion payload. It requires matching source, GitHub run, outcome and archive hashes; a mismatch fails. The finite retry budget and original operation identifier are preserved. The new database function is read-only and unavailable to anonymous and authenticated client roles.

Independent source review found no blocking issue. The regression check passed 19 Python, 56 Deno and 18 PostgreSQL tests, plus type checking. These include lost-response and mismatched-receipt fixtures. A fresh growth update also used receipt recovery during hosted execution; its captured log and archive hashes identify the original request and operation.

The repair leaves calculations, the interface and saved PDF bytes unchanged. The version 1.11.6 offline archives retain their original producer, `b343d9d1c704cfe5f3c4fe61ccef1ae3e679e406`. Fresh hosted results are identified separately in the accompanying GitHub verification and artifact manifest.
