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

Status: implementation, review, and source-release validation complete. The entries below retain the review checkpoints.

Implementation: ADB, APK verifier, GUI, service/CLI/demo written independently; all scoped tests pass as of latest checkpoint.
REA: actual rea-agents@6.10.1 managed artifact/member CLI ran, evidence retained outside release; details in docs/REA-NOTES.md.
Review round 1: five Important boundary findings fixed; rereview closed them. Remaining Minor ADB output cap being fixed.
Review round 1: three Important service findings fixed (bind restore preview target, retain partial install progress for all expected errors, factual postwrite error reporting); all23 service tests green; rereview approved.
Graphical validation: Xvfb demo end-to-end UI smoke passed; screenshot retained. Hardware untested.
External tool validation: actual Google BuildTools36/JDK21 accepted signed specimen and rejected modified copy. No specimen executed or shipped.

Whole-branch review of b7b4942: no Critical or Important findings; one Minor FIFO preview availability issue assigned for final fix wave. ADB output cap reviewed and accepted.
Root independently repeated rendered demo smoke from shipped tests/gui_smoke.py; passed. Source-only archive extracted to fresh tempdir, internal SHA256 manifest verified, CLI smoke and all74 tests passed.
Ruling: Preserve the local feature branch and deliver a source ZIP; no remote publishing or merge requested.

Final fix: both APK preview read paths now reject non-regular descriptors without blocking on POSIX FIFOs. Two regression tests reproduced the original timeout and pass with the fix. The independent reviewer reran both and closed the finding. No findings remain open from the recorded reviews.
Final source validation: all 76 tests, compileall and git diff --check pass. No physical tablet or Windows execution was performed. Preserve the complete source and provide setup instructions; do not claim virus-free certification or full Fire Toolbox feature parity.
