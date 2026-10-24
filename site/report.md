# steward — 2026-10-24 17:14 UTC

**7 repositories · 60 ok · 2 warnings · 1 failures**

| repository | state | what is wrong |
|---|---|---|
| `concord` | ok | — |
| `docket` | ok | — |
| `hourglass` | ok | — |
| `naam` | warn | no CI workflow<br>tests exist but this tool could not run them |
| `sprout` | ok | — |
| `steward` | FAIL | 2 possible secret(s) committed |
| `threshold` | ok | — |

## Failures in detail

- **steward** — 2 possible secret(s) committed
  - `tests/test_steward.py: GitHub fine-grained PAT (github_p…); tests/test_steward.py: GitHub fine-grained PAT (github_p…)`
