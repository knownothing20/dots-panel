# Private backup protocol

This protocol separates local preparation from authenticated storage operations.
It does not upload, start a scheduler, store credentials, restore over production,
or guarantee a storage provider's retention. A configured platform task must
perform the Library operations and check their actual results.

## Recovery scope

Keep SOURCE and DATA separate. A recovery point needs the selected source tree,
an SQLite online-backup snapshot, its registered output files, selected inputs,
configuration, a complete file manifest, and every referenced content object.
Each file has a relative restore path, byte length and SHA-256. A complete manifest
defines the current set: absence in a later manifest does not delete the file
from older recovery points. Never garbage-collect packages while an index still
references their contents.

Do not describe this as a whole-computer backup. Browser sessions, credentials,
account-installed Skills, platform executor sessions, live scheduler state and
unregistered external project directories are outside this scope. The panel's
Skill catalogue and agent observations are records, not copies of those services.
Export user-authored Skill source only through an explicitly selected, authorized
source; a catalogue row does not contain the Skill implementation. Recheck actual
platform identities after recovery. Do not recreate schedules from database rows.

Exclude raw diagnostic logs, process/PID files, caches, generated render frames,
credentials and recursively embedded prior backups. Keep a reviewable exclusion
list. Unfinished work needs an explicit checkpoint of its source, scene, model
and required small assets: a temporary directory is not a reliable archive.
Select such files explicitly; do not sweep every task's temporary directory.
Missing required files must block a claim of complete recovery.

A Library-backed media reference must pin all of: Library identity, immutable
file/version identity, SHA-256, size and restore path. An ID that follows the
latest version is insufficient. Verify downloaded bytes, not just metadata.
Keep historical versions required by a retained recovery point. If their bytes
are unavailable, disclose the gap rather than replacing them with a newer file.

## Publication transaction

1. Read the current private index and retain its Library identity and version.
   Ensure no earlier attempt has an unresolved storage result. Reconcile it first.
2. Validate existing SOURCE, DATA, database, installation identity and baseline
   counts. Missing/reset sources, unexpected identity changes or a substantial
   reduction are blockers. Never initialize an empty application to make a
   backup succeed. Explicit first-time bootstrap is distinct from recovery.
3. Prepare an SQLite snapshot using `sqlite3.Connection.backup()` with the source
   opened read-only. Check integrity and foreign keys. Select artifacts from that
   snapshot and verify their recorded hashes. Check mutable selected files for
   changes while freezing. This is not an atomic transaction across all folders.
4. Compare a complete content manifest with the last committed point. If bytes
   are unchanged, skip upload. SQLite is compared as complete snapshot bytes;
   there is no semantic table/row filtering. A database change can trigger a point
   even when the visible business meaning appears unchanged. Keep journals,
   packages, locks and local index mirrors in a separate excluded state root.
   Do not write routine successful-check heartbeats/runs to the panel database,
   because those writes themselves trigger another point. Notification-state
   changes that are explicitly covered can enter the next hourly point.
5. Pack only new content objects, splitting large files into bounded chunks.
   Every package must be strictly smaller than 19,000,000 bytes. Reused objects
   must remain pinned to a confirmed package, version and hash. The recovery
   dependency set includes old packages still referenced by the current manifest.
6. Verify an isolated restoration before publication. Upload through the current
   supported Library workflow to the authorized private destination. Inspect
   every per-file result. Unknown results require reconciliation, not blind retry.
7. Verify stored bytes and dependencies. Generate a candidate index only after
   the complete restoration has passed. Replace the existing index using its
   exact identity and `expected_current_version`. A conflict requires rereading
   and reconciling; never remove the guard. Publish the index last.
8. Record the actual index replacement receipt before marking the run committed.
   A local prepared file or successful package upload alone is not a successful
   backup. Preserve the journal through interruption. All retries reuse the same
   run identity and frozen inputs.

Storage operations are not a cross-file atomic transaction. Uploading immutable
packages first and moving the guarded latest pointer last prevents partially
uploaded sets from becoming the advertised recovery point. Unreferenced staged
packages may remain after failure; leave them in place until authorized cleanup.

## Scheduling and retention

One existing hourly platform task may perform its authorized progress check and
then run backup preparation serially. Source availability is checked on every
run; the schedule itself does not preserve the cloud computer. If that computer
has reset or is unavailable, preserve the last good off-computer index and report
the blocker. Never make a new empty backup the latest point.

Hourly checks plus content-deduplicated storage limit the normal recovery-point
gap to the time since the last successful changed snapshot, not necessarily one
hour: errors, permissions, execution delays and unavailable files can extend it.
A periodic self-contained consolidation reduces dependency depth, but must be
implemented and restore-tested before it is promised. A sensible initial policy
is hourly changed points and an optional weekly consolidation after measuring
real size and run duration. Daily consolidation can be used if the dataset is
small; it is not intrinsically safer than retaining verified dependencies.

Capture mode is explicit and bound to the preparation request:

- `strict-live` is the compatible default. It additionally requires live SQLite
  `data_version` to remain unchanged through capture. Later progress appends can
  therefore block a preparation whose SQLite snapshot is otherwise consistent.
- `database-snapshot-cutoff` freezes a consistent SQLite snapshot first and uses
  only its tasks/artifact rows for selection. Later live database writes are
  deferred to a later backup and do not invalidate this snapshot. This does not
  permit changes to already-selected source, inputs, configuration, checkpoints
  or artifact bytes. File rehashing, selected-set checks, source/DATA/database
  identity checks, secret/type checks and anomalous-reduction checks still apply.

Neither mode is a filesystem-wide transaction or a whole-computer freeze. A
newly registered output after the cutoff is outside that snapshot's membership;
changes to an existing selected input/output can still block it. Never weaken
the mode or change a locked run's parameters to make an interrupted run pass.
Older default-mode journals remain resumable with the default mode. For a
strict-live database-change blocker, use at most two bounded retries, retaining
the same preparing journal and last good remote index. Do not retry forever or
stop unrelated work. The controller must select cutoff mode only after verifying
that the installed module supports it; a source candidate does not install it.

The manifest records separate database-backup and file-capture windows. Database
backup completion is a cutoff upper bound, not a promise that every transaction
committed before that timestamp is included. A same-mode retry while still
`preparing` may recapture inputs; a `prepared` retry reuses the frozen bytes.
Mode participates in content deduplication, while these observation timestamps
do not. These distinctions must remain visible in status reports.

Retention is a proposal, never deletion authorization: for example, keep 7 days
of hourly points, 30 daily points and 8 weekly points. First measure actual growth
and check provider limits. Preserve old points and every referenced package until
an approved retention operation proves that no retained point depends on them.

Report the first failure and material changes in its cause. Deduplicate repeated
alerts by a stable failure fingerprint, and send one recovery notification after
the next successful run. Keep this notification state outside the disposable
computer if the platform supports it; otherwise disclose that resets can repeat
an alert. Do not put credentials or private content into a scheduler prompt.

## Restoration and cutover

Resolve the selected index and exact versions, then download its independently
stored recovery runner and policy. Verify the runner's pinned SHA-256 before
executing it. The runner is a standalone standard-library program; restoration
must not depend on the old SOURCE tree or its PYTHONPATH still being available.
Materialize all remaining dependencies.
Verify package hashes, safe relative paths, duplicate names, links, decompressed
sizes, content hashes and the SQLite integrity/foreign-key checks. Restore only
to a newly created private directory; never overwrite production or an existing
partial restore. Use a fresh destination when retrying an interrupted restore.
Create every intermediate restore directory with private permissions (0700),
including SOURCE and DATA themselves; do not rely on the process umask. Restored
files use their manifest's private modes (0600 or executable SOURCE files 0700).

Inspect the restored application with the matching source version. `doctor` is
read-only; `status` also reads without migration. Explicit `init` may migrate
older databases, so test it on an isolated copy and record any changes. Never run recovered PID files. Validate
the UI separately when a desktop is available. Obtain explicit user approval
before changing the production launcher or switching active DATA.

Legacy selected checkpoints may have known omissions and an ordered incremental
chain. Preserve that chain and its manifests. A new independent v2 point does not
retroactively repair missing legacy history or prove that every old artifact was
preserved. Record the migration boundary and last verified legacy index.

## Local command interface

The implementation is `src/dots_panel/backup_protocol.py`. It uses the standard
library and a POSIX writer lock. All paths below are operator-supplied placeholders.
The state root must be outside both SOURCE and DATA. Normal scheduled calls must
never supply `--bootstrap`; first-time initialization/migration is an explicit
operator step. Bootstrap writes a persistent identity under DATA/config.

```sh
export PYTHONPATH="$SOURCE/src"
python3 -m dots_panel.backup_protocol --help

# First independent point; LEGACY_INDEX may be the selected legacy index.
python3 -m dots_panel.backup_protocol prepare \
  --source "$SOURCE" --data "$DATA" --state "$STATE" \
  --policy "$POLICY" --previous "$LEGACY_INDEX" \
  --bootstrap --identity "$CONFIRMED_INSTALLATION_ID" --run-id "$RUN_ID"

# Subsequent point; PREVIOUS is the committed envelope or hydrated local state.
python3 -m dots_panel.backup_protocol prepare \
  --source "$SOURCE" --data "$DATA" --state "$STATE" \
  --policy "$POLICY" --previous "$PREVIOUS" --run-id "$RUN_ID"

# Optional tested mode for workloads with ongoing database progress writes.
# Choose this when starting a new request; never change a locked run's mode.
python3 -m dots_panel.backup_protocol prepare \
  --source "$SOURCE" --data "$DATA" --state "$STATE" \
  --policy "$POLICY" --previous "$PREVIOUS" --run-id "$NEW_RUN_ID" \
  --capture-mode database-snapshot-cutoff

# PACKAGES must contain every package referenced by this manifest, including
# reused packages. EXTERNAL must contain exact restore-relative external bytes.
python3 -m dots_panel.backup_protocol verify \
  --snapshot "$RUN_DIR/manifest.json" --packages-dir "$PACKAGES" \
  --external-dir "$EXTERNAL" --report "$RUN_DIR/verification.json"

# Only after actual platform uploads and download/hash verification:
python3 -m dots_panel.backup_protocol commit-index \
  --run-dir "$RUN_DIR" --receipts "$RECEIPTS" \
  --previous "$PREVIOUS" --expected-current-version "$VERSION" \
  --index-library-file-id "$INDEX_ID" \
  --verification "$RUN_DIR/verification.json" \
  --packages-dir "$PACKAGES" --external-dir "$EXTERNAL"

# Publish candidate-index.json using the real platform CAS tool, then run the
# same command with --platform-receipt "$INDEX_RECEIPT". No shell upload exists.

# After loss of local state, rebuild it from downloaded current index bytes and
# current platform metadata. This is not proof of a historical CAS transaction.
python3 -m dots_panel.backup_protocol hydrate-index \
  --candidate "$DOWNLOADED_INDEX" --platform-receipt "$READBACK_RECEIPT" \
  --output "$PREVIOUS"

python3 -m dots_panel.backup_protocol restore \
  --snapshot "$SNAPSHOT" --packages-dir "$PACKAGES" \
  --external-dir "$EXTERNAL" --destination "$NEW_PRIVATE_DIRECTORY"
```

Omit `--external-dir` only when the manifest has no external references. For a
brand-new index without a legacy point, omit `--previous`, use the explicit
bootstrap step, and use `absent` for the first index version. Legacy migration
locks the actual existing index ID and observed current version. The suffix
“v10” of a Library file is a file version, not the JSON schema number.

Policy supports five lists:

- `checkpoints`: exact `SOURCE/...` or `DATA/...` paths up to 2 MB; larger selected
  files require `{path, sha256, size_bytes}` records and are limited to 32 MB
- `reviewed_binary_sha256`: explicit hashes of reviewed opaque binary content;
  this is a review record, not permission to bypass a detected secret
- `external_files`: exact `{file_id, library_file_id, version, sha256, size_bytes,
  restore_path}` records; versions are nonnegative integers
- `excluded_outputs`: exact selected output paths with intentional coverage gaps
- `excluded_inputs`: exact files beneath registered task inputs, with intentional
  coverage gaps; directory/glob exclusions are rejected and omitted bytes are
  not read. A deliberately omitted file may already be absent after restoration;
  retain that fact in the audit instead of requiring a fake placeholder. Keep
  reference notes, URLs and any prior hash evidence separately

Archive filenames alone do not establish backup semantics. A registered editable
project called a checkpoint remains selected. Use explicit reviewed policy
entries for actual old backups; a detected nested backup structure requires
review rather than silently dropping an ordinary deliverable.

If an approved working file changes during an early preparation, do not rewrite
the locked request. `abandon-preparing` is a narrow recovery operation: supply
`--run-dir`, `--expected-request-sha256`, `--no-remote-actions`, `--reason` and
`--evidence`. It acquires the same writer lock and permits only a preparing run
with its own guard and no ZIP, upload plan, receipt or remote-action evidence.
It retains every file and the abandoned journal, releasing only that run's
guard. The old run cannot be revived. Re-review the same approved paths before
starting a new run; an hourly controller may do this at most once per invocation.
Never use abandonment to resolve an uncertain upload or to bypass a secret,
identity, permission or scope problem.

The normalized policy, standalone recovery runner, coverage and privacy-audit
files are part of the upload plan and receive fixed references in the candidate
index. Temporary-directory hints show names
and direct-child counts only. They cannot prove that every unfinished project
has been checkpointed. Check the coverage report before the first publication.

Upload receipts must exactly match the generated plan's filename, operation ID,
hash and size, and carry confirmed immutable platform identities plus a path to
the actually downloaded bytes. The index receipt must match the CAS target,
expected version, candidate hash and downloaded bytes. These are assertions
made by the trusted platform operator, not cryptographically authenticated
receipts the offline module can independently fetch. Never fabricate them from
local originals or mark an unknown platform response confirmed.
