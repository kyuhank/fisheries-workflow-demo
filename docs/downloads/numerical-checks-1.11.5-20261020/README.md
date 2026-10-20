# Preserved native comparison evidence for release 1.11.5

This evidence package describes actual native public-data executions on **14 October 2026**, rechecked by reading and hashing retained files on **20 October 2026**. No model, build or hosted dispatch was rerun during this recheck.

`comparison-evidence-1.11.5.json` is a derived summary. The two `.log` files are unchanged original unittest stdout. Hashes identify the original execution receipts and full logs; private launcher bind paths, host/routing metadata and task context are excluded from this package.

The growth change 0.30→0.35 executed 10 jobs and matched a separate fresh 22-job workflow. The subsequent buffer change 0.8→0.6 executed 3 jobs and matched another separate fresh 22-job workflow. Each comparison has 22 byte-identical numerical output files. The final release 1.11.5 offline archive was also reproduced and compared successfully; all 22 numerical output files are byte-identical to its saved 2021 reference.

Selective tests ran coordinator `b7bbb33d54d5ae074269d186a7384deceb6ec4e8`. Its R/QMD, data, numerical verifier, test oracles, workflow engine and adapters are byte-identical to released producer `6dc2b71b24c946b17f05c93fe4d7810e29c36d1e`. The CPUE pin change to `6ae03144434e26a8e70a403f4384bf8251b4eb8f` updates only its README; the coordinator rendering change removes `.quarto` scratch cache after rendering. Public delivery `361219f17e4ff70bcfa212454ecce23fc555c993` changes only generated docs from producer 6dc.

The tested current public CPUE B formula includes year and quarter. Earlier release 1.11.1 used year-only CPUE B, so its comparison evidence should retain its earlier-source label. These local native comparisons do not imply that each hosted run bundle was separately replayed locally, scientific model approval, or a performance benchmark.
