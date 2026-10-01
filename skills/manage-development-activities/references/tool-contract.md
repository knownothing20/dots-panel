# Supported Task and Panel Contract

## Persistent task capabilities

Use the current tool schemas as authoritative. The baseline public cloud task interface offers:

- `cloud_threads.list_environments`: list computers/remotes and saved coding environments; inspect connection and authorization status.
- `cloud_threads.create`: create a durable task using either `environmentId` for an authorized connected computer/registered Remote or `environmentConfigId` for a saved coding environment. Do not pass both. Omitting selectors uses the documented default desktop route; it does not provision an independent task on the assistant's own cloud executor. Use that default only when its documented requirements are verified.
- `cloud_threads.read`: read a supported child task's latest recorded outcome and messages. Its access scope is restricted; a thread ID alone does not guarantee readability.
- `cloud_threads.send_message`: continue a task by its returned ID, starting a turn when idle or steering it when running.
- `cloud_threads.list_threads`: reconcile an uncertain creation result; listing visibility is not proof that `read` will support that task.

Do not interpret an internal worker's task name as a persisted cloud thread ID. Do not start a real task merely to test this contract. Test with isolated panel fixtures and documented sample inputs instead.

A saved cloud environment, a user's desktop/Remote, and the assistant's own cloud executor are distinct. If no saved cloud environment is listed, do not invent its ID or use `environmentId` to target the assistant's executor. Honor explicit environment choices and obtain any necessary authorization before using a different route.

## Panel binding model

Bind one existing panel `task_id` to one actual execution thread. Expected fields:

- `source_type`: `cloud_thread` or `codex_thread`, based on actual provenance
- `thread_id`: actual returned persisted thread ID
- `environment_kind`: `cloud`, `desktop`, or `remote`
- `environment_id`: actual selected/returned environment identifier when available; do not invent one
- `observed_status`: `created`, `running`, `completed`, `failed`, `interrupted`, or `unknown`
- `observed_at`: time of the source observation, not an invented execution time
- `verified_url`: optional verified HTTPS URL; do not construct a guessed platform URL
- `synced_at`: time the panel imported the observation
- `sync_mode`: `manual`

Treat the CLI's refusal to replace a different thread binding as a safety check. Resolve mismatches rather than forcing a rebind. Do not put absolute local paths, credentials, or machine-specific configuration into reusable skill files.

## Panel CLI operations

Verify the configured panel CLI's `--help` before using these operations; inspect the installed contract if it differs. Set `SOURCE` to the installed panel source directory and `DATA` to its private data directory. Use `sh "$SOURCE/scripts/start.sh" --data-dir "$DATA" --help` to verify configuration. Run it only in the authorized environment.

Bind an existing task:

```text
sh "$SOURCE/scripts/start.sh" --data-dir "$DATA" bind TASK_ID --source-type cloud_thread --thread-id ACTUAL_THREAD_ID --environment-kind cloud --environment-id ACTUAL_ENVIRONMENT_ID --observed-status running --observed-at OBSERVATION_ISO_TIME
```

Omit `--environment-id` only when the verified provider has no such identifier. Add `--url VERIFIED_HTTPS_URL` only if the URL was returned or verified. Choose environment kind and status from actual observations. The current panel URL allowlist accepts HTTPS links on `chatgpt.com`, `chat.openai.com`, or `codex.openai.com`; omit a link outside the supported allowlist rather than rewriting it. The CLI validates metadata structure but cannot establish that a thread exists: verify its identity through the official create/read result first.

Ingest a sanitized incremental event:

```text
sh "$SOURCE/scripts/start.sh" --data-dir "$DATA" ingest TASK_ID "User-facing factual summary" --source-event-id STABLE_EVENT_ID --role assistant --stage implementation --state in_progress --observed-at OBSERVATION_ISO_TIME --observed-status running
```

Use the installed CLI's supported stage and state values. An ingest requires an existing binding and deduplicates by `(task_id, source_event_id)`. Repeating the same event must not produce another timeline entry. Do not pass hidden process text in `MESSAGE`.

These operations record observations; they do not poll the platform, grant access, create cloud sessions, or guarantee automatic synchronization. Make this distinction visible in any status explanation.


## Lifecycle and evidence-bearing completion

Use the installed CLI help as authoritative. New runs require a valid closeout record on every success path, including legacy-named finish and transition succeeded commands. Migration preserves historical run flags; do not claim older completions passed a gate that did not exist.

```sh
panel transition "$RUN_ID" --status waiting_user --from-status running --reason "$WAIT_REASON" --evidence "$OBSERVED_EVIDENCE" --next-step "$NEXT_STEP"
panel transition "$RUN_ID" --status running --from-status waiting_user --reason "$RESUME_REASON" --evidence "$RESUME_EVIDENCE" --next-step "$NEXT_STEP"
panel artifact-designate "$ARTIFACT_ID" --designation final --evidence "$FINAL_REVIEW_EVIDENCE"
# Only after an actual authorized delivery is observed:
panel artifact-delivery "$ARTIFACT_ID" --status sent --evidence "$DELIVERY_EVIDENCE" --observed-at "$OBSERVED_AT"
panel closeout-record "$RUN_ID" --summary "$SUMMARY" --scope "$VERIFIED_SCOPE" --verification passed --evidence "$CHECK_EVIDENCE" --limits "$LIMITS" --artifact "$ARTIFACT_ID"
# Use the record_id returned by the preceding operation:
panel closeout "$RUN_ID" --record "$RECORD_ID"
```

Use verification untested for an explicitly scoped deliverable that did not include running tests, and explain the limitation; never substitute passed. Failed checks cannot complete successfully. If the authorized outcome has no file, omit --artifact and give --no-artifact-reason. The gate checks latest evidence, final designation, archived content hash and recorded delivery; it never sends or opens the artifact. accepted means transport acceptance, not user approval. user_open_confirmed requires a separate actual observation.

## Read-only setup diagnosis

```sh
panel doctor
```

Run doctor before proposing setup changes. It does not initialize missing DATA, migrate, install, connect an account or configure scheduling. Packaged source availability, account Skill installation, scheduler configuration and verified execution are separate facts. An installation-observe record requires actual evidence through the supported account/scheduler tools. Personal account rules stay personal and outside the project bundle. Do not infer verified setup or execution from a successful source check.
