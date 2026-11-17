# Twenty-pass setup audit — 2026-11-16

Exactly 20 numbered passes were executed. Pass 1 reproduced defects with new
regression tests. Passes 2–20 passed. There were no skipped tests.
The suite grew from 59 tests to 64 as performance features were added.
Across all passes, 1,269 test executions ran; the final suite has 64 passing tests.

Each pass parsed every Python source/test file, checked every shell script's
syntax, ran the installer dry-run, parsed the theme YAML, checked both READMEs
for memory documentation, checked diff whitespace, and ran the full available
test suite in a different seeded order. Passes 4–20 also varied Python's hash
seed. These are repeated automated scans plus the code review recorded below,
not 20 independent human reviews. Repetition cannot prove absence of bugs.

## Confirmed defects repaired

1. Initial memory notes could exceed an existing small character budget. New
   stores now start empty if a seed does not fit; recall instructions remain in SOUL.md.
2. A directory named USER.md or MEMORY.md was accepted as an existing memory.
   Configuration now rejects it before writing other settings.
3. Malformed Ollama catalog responses crashed discovery. They now fall back to
   local manifests.
4. Catalog discovery admitted cloud-tagged models, remote-model entries, empty
   names, and duplicates. These are filtered from local model discovery.
5. Journal timeouts could supply byte stderr and crash error reporting. Bytes
   are decoded before constructing the recovery message.
6. Direct verification accepted zero/negative context until invoking system
   commands. Invalid contexts are now rejected at argument parsing.

The README's stale 64K default was also corrected to the existing 128K setting.
Regression checks additionally cover custom model registries, existing empty
memory files, YAML aliases, symlinks, read-only preflight, atomic-write failure,
backups, permissions, custom homes, shell failures, and repeat-run preservation.

## Performance work

The default stays at 131,072 tokens as requested. Existing Flash Attention,
Q8 KV cache, one parallel request, one loaded model, and GPU UUID selection
remain. Keep-alive increases from 10 to 30 minutes to reduce reload delays;
it does not improve steady-state decoding and retains GPU memory longer.

benchmark.py measures three warmed generation samples, median decoding tokens/s,
load/total duration, and model placement. It excludes warm-up from the median.
Verification reports partial CPU offloading when the API provides allocation
sizes. An optional 32K speed preset exists but is NOT selected or applied.
No quality-reducing cache setting, different model, or reduced context was
silently enabled. The 128K default is preserved in config.sh.

## Limits and applying the changes

The changes are in the repository, not applied to the running Ollama service.
Local HTTP and systemd access were denied by this environment, so live ROCm
inference, model placement, and tokens/s could not be measured. Service install,
restart, download, and inference failure paths used simulated commands/responses.
No real package upgrade, model download, service restart, or GPU benchmark ran.
The tests do not establish a performance improvement or end-to-end Hermes tool
calling quality.

To apply the default 128K configuration on the host, from the script directory:

```sh
PERFORMANCE_PROFILE=custom bash setup.sh --tune-only
```

This restarts Ollama and verifies it before updating Hermes. Start a fresh
Hermes session afterward. To measure 128K performance separately:

```sh
python benchmark.py --model qwen3-coder:30b --context 131072 --output benchmark-128k.json
```

## Exact pass ledger

| Pass | Tests | Failure records | Error records | Result |
|---:|---:|---:|---:|---|
| 1 | 59 | 3 | 7 | Defects reproduced |
| 2 | 59 | 0 | 0 | PASS |
| 3 | 63 | 0 | 0 | PASS |
| 4 | 64 | 0 | 0 | PASS |
| 5 | 64 | 0 | 0 | PASS |
| 6 | 64 | 0 | 0 | PASS |
| 7 | 64 | 0 | 0 | PASS |
| 8 | 64 | 0 | 0 | PASS |
| 9 | 64 | 0 | 0 | PASS |
| 10 | 64 | 0 | 0 | PASS |
| 11 | 64 | 0 | 0 | PASS |
| 12 | 64 | 0 | 0 | PASS |
| 13 | 64 | 0 | 0 | PASS |
| 14 | 64 | 0 | 0 | PASS |
| 15 | 64 | 0 | 0 | PASS |
| 16 | 64 | 0 | 0 | PASS |
| 17 | 64 | 0 | 0 | PASS |
| 18 | 64 | 0 | 0 | PASS |
| 19 | 64 | 0 | 0 | PASS |
| 20 | 64 | 0 | 0 | PASS |

Pass 1 includes multiple failing subcases for the same root defect. Its 3 failure
records and 7 error records correspond to the six root defects listed above.

[Machine-readable records and per-pass file hashes](results.json) ·
[Complete test logs](test-logs.txt)
