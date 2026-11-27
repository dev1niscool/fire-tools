# SDD ledger — plan: docs/superpowers/plans/2026-11-27-parity.md

Ruling: User opts out of questions and delegates decisions, and now explicitly authorizes GitHub publication; proceed without another approval flow.
Ruling: Dedicated task checkout and feature branch preserve previous release; disjoint agent ownership permits parallel work under developer multi-agent requirement.
Ruling: Existing dev1niscool/fire-tools is private and contains only an initial README. Preserve visibility and remote history; no force push.
Ruling: Feature expansion includes generic original workflows and independent source helper. No unsupported claim that a firmware-denied action can be made to work.
Baseline: 76 tests pass at 95fe9e4. Task 1–5 pending; research ongoing.

Implementation checkpoint: package19 focused tests, device24 focused tests, GUI8 tests + both rendered smokes, helper6 tests + real SDK compile/sign verification, extra16 focused tests pass. Root CLI7 tests and release3 tests pass. Full integration validation follows all parallel changes.
Task1 review: five Important issues; fix round1 dispatched to original package implementer. Preserve undo on failed first write; report partial restore; recover stock launcher without current HOME; verify installed replacement APK; require explicit updater targets. Root added OTA package selectors.
Ruling: The OTA brief requires explicit target selection. Remove auto-all on empty input and expose selected installed updater packages in both interfaces; no scope expansion.
Tasks2/3/4: independent scoped reviews underway. Task5 integration adds ExtraWorkflows and source-only companion packaging; GitHub Actions checks Linux/Windows Python3.11/3.13 after authorized upload.

Task1: fix round1 complete, all five Important findings addressed; independent rereview approved; 30 focused package tests pass. Package journal also uses pinned directories.
Task2: fix round1 closed four findings, with remaining AppOps output case and staging cleanup/lock-message issues; fix round2 addressed all three; independent rereview approved. 38 device tests and canonical lock-message regression independently passed.
Task3/4: GUI selection-race and helper API23 notification gap fixed; independent rereview approved. Helper now minAPI24, normal desktop minAPI23 unchanged. Helper SDK rebuild and root verifier confirm exact package/minAPI24/signer, original binaries never executed.
Task5: ExtraWorkflows first review found accepted-command reporting, journal entry changes, no-write undo drift, endpoint reserved names, and GUI stale transport selection. Utility implementer fixes first four; GUI implementer fixed selection clearing and passed rendered reconnect regression. Scoped rereview pending.
Root verification: local Xvfb process from prior agent expired; restarted a test-owned server and reran both GUI smoke scripts successfully. Initially selected the prior API23 helper artifact by filename; used the recorded rebuilt API24 artifact and verified its signature/metadata/hash. These were test environment/artifact selection corrections, not product fixes.
GitHub: origin/main fetched; existing README is only '# fire-tools'. Preserve its history through merge and keep private visibility. Publication remains pending final verification/review.

Task5: fix round1 closed all five ExtraWorkflows/integration findings. Independent reviewer approved after 29 focused utility tests, advanced GUI tests and actual rendered reconnect/reselection test. No open findings remain from scoped reviews.
Integration checkpoint: root independently ran 202 tests with local JDK, no skips; compilation and whitespace checks pass. Full source-path scan found no bundled EXE/DLL/JAR/APK or private signing keys. Root refreshed and visually inspected the desktop screenshot. Final whole-branch review follows before upload.
