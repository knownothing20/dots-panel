# Recovery guide

Use the [private backup protocol](private-backup-protocol.md) for the supported
offline verification and restore commands. Installation guidance is in
[Agent setup](agent-setup.md), and optional recurring checks are described in the
[hourly backup template](hourly-backup-agent-template.md).

## If the workspace is unavailable

A missing SOURCE or DATA directory is a recovery blocker. Record what is
actually observable; do not infer a daily reset, a fixed retention period or a
particular host failure. A scheduled check cannot preserve an unavailable cloud
computer by itself. Keep the last successful off-computer index and its complete
dependency set. Never initialize empty DATA or replace that index to make a
backup run pass.

## Restore into a separate private directory

1. Select a known recovery point and retain its exact Library identity and
   version. Resolve every immutable package, external file, policy and recovery
   runner referenced by the index. Read the index's coverage and exclusions;
   a partial or selected backup is not a whole-computer backup.
2. Verify the standalone runner's pinned SHA-256 before running it. Materialize
   the required bytes through the supported Library workflow and verify package
   sizes/hashes. Do not substitute newer mutable files for missing pinned ones.
3. Use a newly created private restore destination, separate from both backup
   storage and any production installation. Never overwrite existing data or
   retry into an incomplete restore. Every restore directory, including
   intermediate SOURCE and DATA roots, must be private (0700); files retain
   manifest modes (0600, or executable SOURCE files 0700).
4. Verify safe paths, all file hashes/sizes, SQLite integrity and foreign keys,
   schema/table counts, installation identity, and registered artifact coverage.
   Retain the actual verification result with its observation time and limits.
5. Use the matching source version to run read-only `doctor` with an absolute
   DATA path. Test `status` or migration-capable commands on a separate copy;
   they may change older database schemas. Check the user interface separately
   when a graphical desktop is available. Test counts belong to that actual
   validation run and are not pre-filled guarantees.

## Review before activation

Recovery reconstructs saved files and records. It does not reconnect accounts,
restore browser sessions, revive executor sessions or duplicate platform
schedules. Historical running/idle observations do not establish current
execution. Never execute recovered PID files. Recheck supported platform state,
and label unavailable observations as unknown.

Keep the verified restore separate until the user explicitly approves switching
the launcher or active DATA. Confirm the target, source compatibility, remaining
gaps and rollback location before activation. Do not delete the old installation
or retained recovery points without separate authorization.

Publish only generic source and documentation. Private task history, Library
identities, deployment paths, account information and recovery reports remain
outside the public repository.
