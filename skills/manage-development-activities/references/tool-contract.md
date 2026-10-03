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

### Atomic receipt and dispatch boundary

The coordinator chooses the matching activity and owns receipt. Pass task ID, returned run ID, stable request ID and receipt fields to the worker. The worker verifies and writes the supplied run, never independently starts another. Re-delivering the same request uses the same ID and content; a later authorized request uses a new ID. Do not use a native worker path as a request ID.

```sh
panel receive "$TASK_ID" --request-id "$REQUEST_ID" --note "$GOAL_AND_SCOPE" --reason "$PENDING_DISPATCH_REASON" --evidence "$REQUEST_EVIDENCE" --next-step "$DISPATCH_NEXT_STEP"
# Existing verified profile only; not an executor availability check:
panel dispatch-check "$TASK_ID" "$PANEL_AGENT_KEY"
# Now use the actual supported dispatch tool. Only after confirmed execution:
panel agent-run-assign "$RUN_ID" "$PANEL_AGENT_KEY" --work-type development
panel agent-observe "$PANEL_AGENT_KEY" --status running --observed-at "$OBSERVED_AT" --note "$SANITIZED_OBSERVATION"
panel transition "$RUN_ID" --status running --from-status waiting_external --reason "$DISPATCH_RESULT" --evidence "$ACTUAL_EXECUTION_EVIDENCE" --next-step "$IMPLEMENTATION_STEP"
panel status
```

`receive` requires an existing activity. A single SQLite transaction creates the `waiting_external` run, receipt and matching timeline event, with no transient running state. Identical concurrent retries deduplicate on `(task_id, request_id)`; changed content under the same ID is rejected. Retrying a receipt after its run finishes returns that finished run, never reopens it. These are enforced local command properties, not guaranteed Skill triggering or a platform dispatch transaction. Registering the activity and actually dispatching remain separate operations; record and reconcile failures at each boundary. `start` retains its legacy running behavior for already-started execution and does not replace receipt.

For an older installed CLI without `receive`, explicitly record the request first with `activity --stage received --state planned`, then `start` and immediately `transition --status waiting_external --from-status running` with the pending-dispatch reason. This compatibility path is non-atomic and briefly records running: disclose that limitation, reconcile after interruption, and never pretend it dispatches anything. Upgrade only when authorized. There is no supported `queued` lifecycle enum.

`dispatch-check` reads without modifying or initializing DATA. It emits `recorded_conflict` only when the latest explicit run assignment is to a single different activity, that run remains running, and a fresh running profile observation was recorded at or after that assignment. A tied different-topic assignment, missing run, old or pre-assignment observation, primary ownership alone, completed history, idle, and waiting states are insufficient; the result remains `unverified`, never “free.” It never resurrects an older association after a newer terminal assignment. The hint is not a platform lock and cannot eliminate races. Check supported executor state immediately before actual dispatch; record capacity waits rather than steering an unrelated busy worker or stealing its assignment.

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

## Native worker observations and parallel participants

A native dispatch result proves only that supported worker identity/state at that observation. It is not a persisted cloud thread ID. Verify state through the current supported coordination interface; keep runtime identities out of panel text and shared source. Use panel-local friendly profile keys and manually observed timestamps.

```sh
# Only a fixed nickname, never the task title. Omit --portrait to allocate an unused fixed style.
panel agent-register "$PANEL_AGENT_KEY" --name "$FIXED_NICKNAME" --name-en "$FIXED_ENGLISH_NAME"
# Only after matching this profile to the actual executor through supported tools:
panel agent-identity "$PANEL_AGENT_KEY" --source manual --verification observed --observed-at "$OBSERVED_AT" --evidence "$SANITIZED_IDENTITY_MATCH_EVIDENCE"
panel agent-observe "$PANEL_AGENT_KEY" --status running --observed-at "$OBSERVED_AT" --note "$SANITIZED_OBSERVATION"
panel agent-run-assign "$RUN_ID" "$PANEL_AGENT_KEY" --work-type development
panel status
```

Keep panel-local keys unchanged and nicknames/portraits fixed. Never name a new profile after its task or role. For an authorized correction, use `agent-profile KEY --name FIXED_NICKNAME --name-en FIXED_ENGLISH_NAME --portrait CONFIRMED_UNUSED_STYLE`; previous display labels remain in history. `agent-identity` records a match observation, not a platform binding, live connection, permanent executor or future reuse guarantee. Use `--source historical --verification historical` for retained records that cannot currently be matched, with actual inspection time and evidence. The portrait catalog is original code/vector artwork; it provides no identity verification. Without --portrait, new registration allocates an unused style atomically while one is available. Explicit selections and an exhausted 48-style catalog can repeat styles; never merge identities based on matching portraits. Identity provenance uses identity_observed_at; executor state has its separate observed_at.

Use an existing profile for the same verified executor. `agent-run-assign` is idempotent for the same current run/profile/role and permits parallel participants without replacing the activity's primary owner. It returns `assignment_id`. A changed role closes the old immutable episode and creates another. Reconfirming a legacy snapshot creates a new explicit episode; it does not rewrite unknown history. It does not start a worker. Record unknown for unconfirmed/pending initialization. A finished worker turn becomes idle only after observation; waiting or incomplete goal runs remain open. When the installed CLI lacks this operation, record the tracking gap and upgrade only with authorization; never silently overwrite another assignment.

## Current step without a lifecycle transition

```sh
panel progress-update "$RUN_ID" --current-step "$STEP" --result "$RESULT" --next-step "$NEXT" --evidence "$EVIDENCE" --source-event-id "$STABLE_EVENT_ID"
# Only with an actual measured count:
panel progress-update "$RUN_ID" --current-step "$STEP" --result "$RESULT" --next-step "$NEXT" --evidence "$EVIDENCE" --completed 240 --total 576 --unit frames --source-event-id "$STABLE_EVENT_ID"
```

Use the installed help as authoritative. This appends an explicit user-facing milestone without changing lifecycle, primary owner or executor control. Retries with the same ID/content are deduplicated; a reused ID with different content is rejected. Completed and total must be supplied together with a unit and satisfy 0 <= completed <= total. Terminal runs cannot accept new progress. These counts are observations, not computed estimates of overall project completion. Read-only UIs retain assigned identities per run, separately label fresh running observations or older unconfirmed observations, and show recent meaningful steps, but do not synthesize progress from heartbeat or elapsed time.

## Structured follow-up responsibility and read-only audit

Verify the installed CLI help first. These commands record or inspect residual-goal responsibility; they do not control an executor, contact a platform, dispatch work or change scheduling. Use only explicitly authorized existing activities and sanitized user-facing evidence.

```sh
panel followup-checkpoint "$RUN_ID" \
  --source-event-id "$STABLE_SOURCE_EVENT_ID" --observed-at "$SOURCE_EVENT_ISO_TIME" \
  --goal-status incomplete --remaining-scope "$RESIDUAL_AUTHORIZED_SCOPE" \
  --blocker-class internal_handoff --next-owner "$RESPONSIBLE_COORDINATOR" \
  --next-action "$AUTHORIZED_NEXT_ACTION" --recheck-condition "$OBSERVABLE_RECHECK_CONDITION" \
  --evidence "$ACTUAL_RESULT_AND_LIMIT_EVIDENCE"
# Read only; repeat --task-id for every selected authorized activity:
panel followup-audit --task-id "$TASK_ID" --stale-after 3600
# Optional evidence from actual supported executor reads, never invented observations:
panel followup-audit --task-id "$TASK_ID" --executor-observations "$SANITIZED_OBSERVATIONS_FILE"
```

`goal_status` is `incomplete`, `complete` or `unknown`. `blocker_class` is `none`, `internal_handoff`, `external_wait`, `security`, `access`, `approval`, `failure` or `unknown`. Checkpoint fields are `goal_status`, `remaining_scope`, `blocker_class`, `next_owner`, `next_action`, `recheck_condition` and `evidence`. Preserve remaining scope, next owner, concrete authorized next action, recheck condition and evidence separately. The command requires an existing unfinished run. `complete` never transitions to succeeded or replaces closeout/delivery verification. A missing checkpoint is unknown responsibility, not completed scope. On an older CLI, retain these fields as a factual timeline checkpoint and disclose the unsupported structured operation.

Both `--source-event-id` and `--observed-at` are required. The source ID is a verified stable event identity, not a raw runtime path or a random retry ID. CLI observation time is the source event's timezone ISO time (the Store API also accepts a UTC epoch); it cannot predate the run or lie in the future. Retry with the exact same source ID, all fields and observation time. The same event returns its original checkpoint ID, including a delayed retry after a newer event; conflicting content/time under that ID is rejected. A genuinely new state or recurrence requires a new verified source event ID and source time, even when some text repeats. Do not restamp a retry to appear current.

The returned checkpoint event has a UUID identity and immutable content hash; history is append-only. Latest checkpoint selection uses `observed_at` first, then creation time as a tie-breaker. Existing legacy rows with unknown source event/time are preserved and fall back to their retained creation time, never relabelled as observed source events.

`--executor-observations` takes a private JSON file path. Its bounded list has exactly five fields per row: actual panel `run_id`, `status`, `provider`, `observed_at` and `evidence` from supported observations. `status` is `running`, `idle`, `blocked`, `unavailable` or `unknown`; `observed_at` is a finite nonnegative UTC epoch no later than audit time. It contains no raw runtime IDs, task paths, credentials, transcripts or invented platform readings. Provider observation time is distinct from audit time and local registration. Stale/missing/inaccessible platform evidence stays unconfirmed. `--stale-after` accepts 1–86400 seconds (default 3600); executor observation freshness is capped at 300 seconds even when that progress threshold is longer. Verify these bounds in installed help rather than choosing an unbounded exemption.

The returned `dots-panel.followup-audit.v1` envelope has `checked_at`, `task_scope`, `receipts`, `run_count`, `source`, `record_only: true`, `scheduler_hook: not_verified_by_audit` and `backup_result: separate_not_inferred`. Each receipt has `task_id`, `run_id`, `checked_at`, `lifecycle`, `latest_progress_at`, `executor_status`, `executor_observation`, `checkpoint`, `disposition`, `reason`, `next_action`, `notification: not_sent_by_audit` and `record_only`. A missing checkpoint or executor observation is null, never invented evidence. Structured residual scope, next owner and recheck condition are in `checkpoint` when present; when absent the disposition asks the coordinator to supply them.

Disposition vocabulary is `blocked_requires_authority`, `coordinator_followup`, `coordinator_diagnosis`, `coordinator_closeout_check`, `wait_with_owner`, `checkpoint_required`, `needs_executor_observation` and `no_flag`. `no_flag` still includes the reason (`recent_progress`) and the relevant observations; it is not goal completion. Read the full per-run audit output for every selected authorized open run. A useful receipt states disposition, explicit flag/no-flag reasons with observed evidence and freshness, residual goal status/scope, blocker, next owner/action and recheck condition. A “checked” timestamp alone is insufficient. Errors/failures, security/access/approval issues and internal review handoffs trigger review independently of recent meaningful progress, including progress within the last hour. Executor idle plus unresolved/unknown scope must return responsibility to the coordinator. Preserve unresolved failures and dependency errors until direct recovery evidence exists; backup success does not clear them.

The read-only CLI performs a complete explicit scoped SQL read of selected activities, all their open runs and per-run latest progress/checkpoint. It does not use the bounded UI overview (such as its 500-task window), nor scan unrelated activities. Automatic failure hints inspect only the latest `current_step` and `result` for technical `ERR_*` codes (including numeric codes) or `Traceback (most recent call last)`. Evidence prose and an arbitrary “failed” word do not establish failure. Affirmative resolved/cleared/fixed/recovered code context suppresses that text hint; negated resolution never clears it. Explicit checkpoint `failure` remains a separate trigger. These hints aid diagnosis; they neither establish a root cause nor prove recovery.

The hourly inspector only returns safe supported next work to the parent coordinator, who owns continuation under existing authorization. Audit suggestions never authorize auto-dispatch, retry, access changes or bypassing safety. Inspection receipt/coverage and backup result are separate facts. Read the actual current automation prompt through an authorized tool before any proposed edit; if unavailable or denied, do not overwrite, recreate or reschedule it. Bundled source/template changes leave the live hook unverified until an observed natural callback.


## Activity-centered collaboration and immutable attribution

Verify these installed commands before using them. All are local records, not executor dispatch or synchronization.

```sh
panel register "$TASK_ID" --name "$NAME" --project "$LABEL" --kind task --collaboration-mode single
panel activity-structure "$TASK_ID" --collaboration-mode team --reason "$ACTUAL_PARTICIPANT_PLAN"
# Only for distinct deliverables, with an existing root project:
panel register "$CHILD_ID" --name "$CHILD_NAME" --project "$LABEL" --parent-task-id "$PROJECT_ID"
panel agent-run-assign "$RUN_ID" "$PANEL_AGENT_KEY" --work-type design
# Use the actual assignment_id from that result:
panel progress-update "$RUN_ID" --assignment-id "$ASSIGNMENT_ID" --current-step "$STEP" --result "$RESULT" --next-step "$NEXT" --evidence "$EVIDENCE" --source-event-id "$STABLE_ID"
panel assignment-end "$ASSIGNMENT_ID" --reason "$OBSERVED_END"
panel timeline "$TASK_ID" --include-children --limit 100 --offset 0
```

`register --kind project` creates a project record. The existing `project` text is only a label and never implies a parent. `activity-structure` accepts kind, collaboration mode, parent-task-id or clear-parent plus required reason. It rejects missing parents, self-links, nested projects and converting a project with children into a task. Adding scope to a finished project requires a new authorized parent run. Keep any scope changes explicit and reviewable. single/team is independent from task/project; two participants may share one task with no children. Classification is explicit, not inferred from historical records or automatically changed by assignment.

An assignment episode keeps immutable run, agent, role, assignment time and provenance. Ending it records the end once. A terminal run rejects role changes. Legacy migration preserves only its last stored association as `legacy_snapshot`, without inventing earlier roles or authors. Existing participant APIs remain compatible as latest-association projections; historical display uses episodes.

`progress-update`, `log`, `activity` and `ingest` accept `--assignment-id`. New attribution requires an open matching assignment, an unfinished run, and an explicitly verified manual actor identity. Ingestion also requires the actual binding and cannot predate the chosen assignment. For late historical events without a verified open episode, leave authorship unrecorded rather than falsifying it. Attribution freezes actor name, original portrait key, panel-local short ID, role and assignment ID. Local IDs are not platform IDs. Older rows without this evidence remain `historical_unattributed`; never backfill from current ownership. Existing un-attributed ingest retries keep the legacy first-write-wins behavior, while attributed retries reject conflicting content or actor data.

The scoped `timeline` query reads beyond the bounded overview snapshot. Filters `--agent-id`, `--work-type` and `--child-task-id` combine with AND semantics; agent and role filters accept `unattributed`. Each page returns total, offset, limit and has_more. Its read-only local HTTP equivalent is `/api/collaboration-timeline`, with task_id, include_children, agent_id, work_type, child_task_id, limit and offset query parameters. None of these calls fetch platform conversations. A current page or bounded snapshot is not the complete history until pagination is exhausted.

The coordinator remains responsible for actual dispatch and run ownership. Keep one topic per executor even when sibling tasks share a parent. A parent closeout checks every child's latest outcome and all open child runs, then requires its own integration/delivery evidence. Do not silently remove an unfinished child to pass the gate. No separate Agent page, automatic inventory, periodic ten-minute scan or scheduler is part of this workflow.


## Explicit model dispatch and configuration provenance

The coordinator chooses default task execution `gpt-6.1-sol` / `high`, with allowed ceiling `gpt-6-astra` / `ultra`, independently of any review Skill's own settings. Inspect the current dispatch schema. A native example, only when these fields are currently supported:

```javascript
collaboration.spawn_agent({task_name: "implement_scoped_task", fork_turns: "none", model: "gpt-6.1-sol", reasoning_effort: "high", message: "The concrete authorized task and relevant activity/run/request IDs"})
```

Full-history forks inherit settings and do not accept overrides. Durable task routes use their supported `model` / `thinking` fields, not native field names. Setting panel metadata never dispatches or reconfigures a runtime.

The read-only `dispatch-plan` can provide supported default parameter arguments, but it does not execute a task. Immediately after actual dispatch, use current installed help for the configuration-aware assignment API:

```sh
panel agent-run-assign "$RUN_ID" "$PANEL_AGENT_KEY" --work-type development \
  --requested-model gpt-6.1-sol --requested-effort high \
  --config-verification requested --config-provider "$SUPPORTED_PROVIDER" \
  --config-observed-at "$OBSERVED_AT" \
  --config-evidence 'Dispatch accepted requested settings; provider did not expose actual runtime settings'
# Only add these when supported actual runtime evidence exists:
# --actual-model ACTUAL_MODEL --actual-effort ACTUAL_EFFORT --config-verification verified
```

Omit unavailable actual values; never copy requested values into them. If an older installed API lacks these flags, retain a sanitized requested/actual/unknown checkpoint and disclose the structured tracking gap, then upgrade only when authorized. A configuration change creates a new immutable episode, preserving the original assignment and event-time authorship. Local records cannot prove platform settings or guarantee future continuity.


## Explicit requirement cards and status history

Verify the installed help first. Requirement commands are independent of run lifecycle and do not dispatch platform work or control an executor. Use the original current-scope user source ID/time; retain the returned requirement ID in handoffs. All examples use placeholders, never synthetic production records.

```sh
panel requirement-create TASK_ID --summary "$SHORT_ORIGINAL_REQUEST" \
  --source-event-id "$REQUEST_SOURCE_ID" --observed-at "$REQUEST_SOURCE_TIME" \
  --evidence "$RECEIPT_EVIDENCE"
# After actual dispatch, identity and assignment are confirmed:
panel requirement-assign REQUIREMENT_ID --assignment-id "$ACTUAL_ASSIGNMENT_ID" \
  --source-event-id "$DISPATCH_SOURCE_ID" --observed-at "$DISPATCH_SOURCE_TIME" \
  --expected-owner-event-id 0 --evidence "$DISPATCH_EVIDENCE"
panel requirement-link REQUIREMENT_ID --link-kind run --target-type run \
  --target-id "$RUN_ID" --source-event-id "$RUN_LINK_SOURCE_ID" \
  --observed-at "$SOURCE_TIME" --evidence "$EXPLICIT_ASSOCIATION"
panel requirement-list TASK_ID --scope all
panel requirement-transition REQUIREMENT_ID --status in_progress \
  --expected-event-id "$CURRENT_EVENT_ID" --source-event-id "$START_SOURCE_ID" \
  --observed-at "$START_SOURCE_TIME" --evidence-kind start \
  --evidence-ref "$ACTUAL_START_REFERENCE" --evidence "$START_EVIDENCE"
# Link a real result before handing it to acceptance:
panel requirement-link REQUIREMENT_ID --link-kind result --target-type progress \
  --target-id "$RETURNED_PROGRESS_ID" --source-event-id "$RESULT_LINK_SOURCE_ID" \
  --observed-at "$RESULT_SOURCE_TIME" --evidence "$RESULT_EVIDENCE"
panel requirement-transition REQUIREMENT_ID --status pending_acceptance \
  --expected-event-id "$CURRENT_EVENT_ID" --source-event-id "$RESULT_STATUS_SOURCE_ID" \
  --observed-at "$RESULT_SOURCE_TIME" --evidence-kind result \
  --evidence-ref "$RETURNED_PROGRESS_ID" --evidence "$ACCEPTANCE_HANDOFF_EVIDENCE"
# Only after actual authorized acceptance:
panel requirement-transition REQUIREMENT_ID --status completed \
  --expected-event-id "$CURRENT_EVENT_ID" --source-event-id "$ACCEPTANCE_SOURCE_ID" \
  --observed-at "$ACCEPTANCE_SOURCE_TIME" --evidence-kind acceptance \
  --evidence-ref "$ACTUAL_ACCEPTANCE_REFERENCE" --evidence "$ACCEPTANCE_EVIDENCE"
panel requirement-diagnose TASK_ID
```

Read the current returned IDs between commands; do not reuse a stale CURRENT_EVENT_ID. The first owner event expects 0; subsequent assignments use `current_owner_event_id` from requirement-list. Creation may optionally include an already-confirmed assignment. That initial snapshot and original text remain immutable; later `requirement-assign` appends history and updates only the derived current owner/model view. `requirement-transition --assignment-id` attributes the status recorder, not a reassignment.

Link kinds/targets: run→run, progress/result→progress|activity|event, artifact→artifact. Targets must actually exist in the same activity. Explicit event links survive legacy timeline mirror deduplication and must not be transferred to a similar-looking activity row. Source IDs identify retries, not permission. A source conflict or stale expected ID must be reconciled rather than bypassed. A result-status evidence reference must match its linked result target or link source ID; completion requires pending acceptance and a distinct acceptance reference.

`requirement-list` and `requirement-diagnose` use read-only database access and do not migrate. A received card is not proof of dispatch. A state event records the caller's evidence, not proof of blanket authority. Unknown old requirements stay absent unless the user authorizes explicit evidence-backed historical registration. No automatic chat import, model change, schedule update or user acceptance is implied.

## Atomic requirement intake and pending association readback

Check installed help. Both commands are explicit local recording/read operations, never a chat subscriber, platform dispatcher or permission mechanism.

```sh
panel requirement-receive "$TASK_ID" --source-event-id "$SOURCE_ID" --observed-at "$SOURCE_TIME" \
  --summary "$ORIGINAL_SHORT_SUMMARY" --evidence "$SOURCE_EVIDENCE" \
  --reason "$WAITING_REASON" --next-step "$NEXT_STEP"
# Add --run-id only for an explicitly selected matching open run.
panel requirement-sync-status "$TASK_ID"
```

The intake writes requirement, waiting run (unless an existing open run was explicitly selected), run link and immutable receipt in one SQLite transaction. Identical retries return the same requirement/run even after the run later becomes terminal. Changed fields under the same source identity are rejected. Existing exact legacy receipt/requirement records can be reconciled without inventing new IDs; mismatches stop. A terminal run cannot accept a genuinely new intake. Source time and recorded time remain separate. Every multi-item message needs stable per-item source identities, not a new random retry key.

`requirement-sync-status` opens existing DATA read-only without initialization/migration. It reports missing_run_link or assignment_unconfirmed for explicitly recorded unfinished requirements. No missing chat can be inferred from this result; upstream_message_coverage remains not_connected. Uncertain dispatch is still unconfirmed, not evidence to create another worker. Use the existing confirmed assignment API only after actual platform evidence.

The read-only snapshot carries a complete local requirement event feed with separate status/owner counters and DATA identity, not the bounded 500-task overview. UI notifications coalesce repeated changes of one requirement into its latest unread card while the requirement ledger retains all intermediate states. First observation establishes a historical baseline; acknowledged changes do not replay every poll. Persisted unread state is local to the viewer/browser and does not mark a requirement complete. A replacement or rewound DATA establishes a fresh baseline; this is not a claim of cross-backup notification recovery. No HTTP mutation endpoint is added.
