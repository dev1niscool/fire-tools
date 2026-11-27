# SDD ledger — plan: docs/superpowers/plans/2026-11-27-toolkit.md

Ruling: User explicitly opts out of questions and delegates decisions; proceed without design approval wait.
Ruling: New dedicated repository on feat/initial-toolkit provides isolation; no existing repository/worktree to protect.
Ruling: Independent file ownership permits parallel implementation to meet developer multi-agent instruction. Root alone commits; no conflicting files.
Ruling: REA CLI acquisition/analysis authorized; no setup registration or target execution needed.

Preflight interface table:
| Tasks | Shared interface/files | Finding |
| 1 / 3 | DeviceInfo and AdbClient | Exact dataclass/method contracts pinned above; root consumes |
| 2 / 3 | ApkInfo and ApkVerifier | Verifier returns signed identity; service checks Google set and stages |
| 3 / 4 | Toolkit, Plan, ToolConfig | GUI consumes only public APIs; root demo parity required |
| 1 | adb.py/tests only | coherent; timeouts and remote quoting tested |
| 2 | apk.py/tests only | coherent; external tools must verify not merely parse certificates |
| 3 | service/CLI/demo | coherent; plan preview data is rechecked before mutations |
| 4 | GUI/tests only | coherent; async tkinter ownership explicit |
| 5 | docs/package/review | coherent; source-only distribution, no hardware claims |

Status: design and contracts established; implementation pending.
