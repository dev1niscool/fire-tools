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

Implementation: ADB, APK verifier, GUI, service/CLI/demo written independently; all scoped tests pass as of latest checkpoint.
REA: actual rea-agents@6.10.1 managed artifact/member CLI ran, evidence retained outside release; details in docs/REA-NOTES.md.
Review round 1: five Important boundary findings fixed; rereview closed them. Remaining Minor ADB output cap being fixed.
Review round 1: three Important service findings fixed (bind restore preview target, retain partial install progress for all expected errors, factual postwrite error reporting); all23 service tests green; rereview approved.
Graphical validation: Xvfb demo end-to-end UI smoke passed; screenshot retained. Hardware untested.
External tool validation: actual Google BuildTools36/JDK21 accepted signed specimen and rejected modified copy. No specimen executed or shipped.
