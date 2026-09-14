# Reproduce the first repaired source after later source changes

The first 96-checkpoint repair used `frozen_v2`. The working tree now contains a separately labeled amendment, so invoking the original reproduction script directly from the current source correctly rejects its source hashes. Preserve that refusal.

Use the offline staging helper from the repository root:

```sh
.venv/bin/python evaluation/changing_memory_repair_20260914/stage_first_repair_reproduction.py stage \
  --stage /tmp/clara-first-repair-source-NEW \
  --output /tmp/clara-first-repair-collection-NEW
```

Both names must be new. The helper performs no freeze, model request, generation, embedding inference, or collection. It prints a guarded command that first re-verifies the stage and then invokes the **unchanged** `reproduce_collection.sh` from that source stage. Executing that printed command later performs real inference, creates a new freeze/run, and requires new independent blinded reviews of the new answers. Existing scores cannot score a new run.

The stage contains exact copies of the 41 frozen source/configuration/test files plus the two root preparation documents from the first freeze. It imports those copied sources through the existing virtual environment. It shares the installed embedding assets and hashes all three expected asset files offline. Package, Python, device-policy and configuration values are checked against the first freeze. Actual installed model HTTP metadata is deliberately not queried by the offline helper; the unchanged live reproduction script checks model and runtime conditions before collection.

**The entire staged `evaluation` directory is a symlink to the real repository's evaluation directory.** `.venv` also links to the existing repository environment. The global `/tmp/clara-jetson-inference.lock` and all three evaluation lock paths resolve to the same real paths, devices and inodes. Read-only descriptor identity checks acquire no locks and create no lock files. The copied runners retain their original lease and inherited-worker-descriptor checks. Replacing this symlink with a private evaluation directory or copied lock files is rejected because it could bypass experiment serialization.

Shared authored schedules, ledger, protocol, prospective review, authoring files, validation evidence and historical preparation documents are checked against the first frozen copies. The two root documents are copied from the freeze so later workspace-note updates do not change them. The helper pins both the first freeze seal and the unchanged reproduction-script hash, and rechecks shared inputs immediately before the returned command launches the existing script. Drift requires a separately reviewed reproduction setup; this helper does not bypass it.

An offline import smoke test denies network and subprocess calls inside the import-checking child. It verifies that local modules resolve into the staged source, all 41 `runner.sources()` entries match, and the two runner root paths resolve to the isolated source root. It does not initialize a model or embedding session. Partial failed stages are preserved; neither existing stage nor output directory is overwritten. Source and proof files are made read-only without traversing either shared symlink.

The demonstrated stage is `/tmp/clara-first-repair-source-20260914-v1`; its proposed collection output `/tmp/clara-first-repair-reproduction-20260914-v1` was **not created or executed**. The exact guarded command is recorded in `staging_validation_v1/offline_stage_receipt.json`. Five offline protection tests cover existing-output rejection, private evaluation directories, copied-lock-directory symlinks, source drift before import, and actual shared lock identities. Test source is `test_frozen_source_staging.py`; the positive staging command, import/asset proof, helper/test source hashes and validation record are retained in `staging_validation_v1`.

These commands reproduce the targeted development experiment under the frozen first-repair source. They do not provide new experimental observations, held-out validation, power-loss recovery evidence, or spoken performance. Keep all new outcomes, including failures, separate from the first 96 checkpoints and the later cm04 amendment.
