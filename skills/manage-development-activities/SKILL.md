---
name: manage-development-activities
description: Keep each task in one persistent dots-panel activity, maintain its verified executor identity and current work type, and archive reports, images and other deliverables in its private task folder. Use when starting or continuing development or research, recording progress, or producing task files. Reuse verified sessions where supported; never fabricate conversations or claim automatic synchronization.
---

# Manage Development Activities

## Read project rules first

Read the configured panel project's `src/dots_panel/project_rules.json` at the start of task work. It is the versioned, bilingual source displayed in the Rules tab. Distinguish `enforced` checks in current panel operations, `workflow` agreements the executor must follow, and `planned` features that do not exist yet. Do not invent global folders or claim planned software management is implemented. These project guidelines never grant account access or override the user's current instructions or platform safeguards. If the catalog is missing or contradicts actual installed behavior, report the mismatch and use the verified supported workflow rather than claiming compliance.

Keep maintained source projects in their own confirmed project directory. For one-off single-file deliverables, use the task's tmp while drafting and archive the verified deliverable to outputs; do not leave the only output in a cache. The Rules tab is documentation, not a filesystem watcher or a background agent-status integration.

## Establish the activity

1. Identify the concrete development goal, scope, requested execution environment, and completion condition. Treat implementation, debugging, tests, review, and delivery as stages of the same goal.
2. Inspect the configured panel's existing activities and bindings before creating anything. Read the bound session through a supported tool and compare its purpose and latest state with the request. Reuse a matching activity, including later work on a previously completed goal, with a new run rather than reopening a terminal run. Ask one concise question if several bindings could match or the scope is ambiguous.
3. Treat a genuinely separate goal or an explicit request for a separate activity as a new activity. Creating a panel record alone does not create a real execution session.
4. Read the current supported environment and task-tool descriptions. Use [references/tool-contract.md](references/tool-contract.md) for the verified baseline and failure handling. Respect the user's chosen environment and cost constraints. Do not substitute a computer or executor without authorization.

## Receive, dispatch, then verify registration

Ordinary conversation does not need an activity. For an actionable development, research or deliverable request, the coordinator records receipt before delegating or lengthy work. The coordinator owns receipt and run selection; a worker given a run ID verifies and continues it, never creates a duplicate run. Pass the activity ID, run ID and stable request ID in every handoff. If the run ID is missing, reconcile with the coordinator or call `receive` using the same request ID and identical receipt fields; never invent a random retry ID. A genuine later request gets a new request ID and, when the previous run is terminal, a new run in the same activity.

1. Select the matching goal activity, or register one only for a genuinely new goal. Check existing open runs before writing. A genuinely new executable request receives a new run in that activity; ongoing stages, progress or clarifications within the already accepted request continue its existing run. Repeated delivery of the same request reuses its receipt. Distinct stages alone do not require new runs.
2. For newly accepted work, use `receive` from [references/tool-contract.md](references/tool-contract.md). It atomically records a run as `waiting_external` with a factual pending-dispatch reason, evidence and next step. This is a recorded queue, not a platform queue or an invented `queued` status. Read it back before dispatch. On an older CLI use the documented non-atomic compatibility path and disclose its gap.
3. Verify the intended executor's actual identity, current topic and state through supported task tools. If supported, run the panel's read-only `dispatch-check` as an additional narrow recorded-conflict hint. It cannot prove an executor is free or replace platform verification. Never steer an unrelated topic into a busy worker. Keep one execution session on one topic at a time. A matching goal may continue in its verified executor; otherwise use a different available executor. If capacity is unavailable, keep the accepted run waiting with the concrete queue reason and next step rather than silently mixing topics.
4. Dispatch through an actually available, authorized execution tool. In the assistant's authorized cloud environment use a native worker when supported; user-selected desktops, Remotes and saved environments use their supported durable-task route. Do not substitute environments to work around a denial.
5. Immediately after confirmed dispatch, register or reuse its fixed-nickname panel profile (never use the task title or work type as its name) and associate it with the existing run through `agent-run-assign`. Record the actual returned or queried state: running only after confirmed execution, unknown while initialization is unconfirmed. Transition the run to running only with that evidence. Preserve primary ownership and historical participant links. Several participants and several same-goal runs may coexist; every identity remains scoped to its run.
6. Read back the activity, run, participant and observation before long implementation. A failed or uncertain dispatch is still recorded immediately, with the real blocker and next authorized step. Keep recoverable waits open; record failed only for an established terminal failure. Reconcile uncertain tool results before retrying dispatch. If panel writing fails, repair registration without starting duplicate workers and disclose the tracking gap.

Keep native runtime identities in authorized coordination context only. Never put their paths, raw identifiers, transcripts, private instructions or hidden reasoning into the panel, handoff documents or portable source. A friendly profile is not an independent conversation. Bind a platform conversation only when an actual persisted ID was returned.

## One topic, safe continuation and independent review

A verified executor can continue the same goal's implementation, tests and fixes. Reuse is conditional on its actual current topic and availability, not merely its old name or activity ownership. If the former worker is now busy on another topic, start a different available executor for the original goal and give it the sanitized checkpoint. If none is available, record waiting and explain the constraint. Never reopen a finished run or silently replace a durable binding; preserve original identity and history, and use the supported replacement procedure or report its absence.

For independent review, use an executor that did not author or modify the work under review. Its assignment is review and its output is findings with evidence. A producer's tests remain useful but do not count as independent review. Revisions return to the producer or a separately assigned implementer, then go back for review. Record reviewer and producer on the same goal, with the relevant run association.

Long-term context retention has no fixed guarantee. At meaningful stage boundaries, before waiting, and before changing executors, save a concise user-facing checkpoint in the same activity: goal, constraints and authorization limits, completed outputs or verified references, checks and unresolved limits, current blocker, and next authorized step. Preserve deliverable identity; do not claim full conversation retention. Exclude hidden reasoning, internal instructions, raw transcripts, secrets and runtime paths. A replacement executor reads and verifies this checkpoint and relevant deliverables before continuing.

## Create or reuse a durable session when applicable

- For an existing binding, use its actual thread ID with supported read and message tools. Continue that session for same-goal stages only after verifying it is not occupied by another topic. A stage change or another message alone is not a reason to create a new activity.
- For a new goal requiring a durable external execution environment, discover eligible connected computers/remotes and saved coding environments. Select only an available, authorized environment that satisfies the request. If none fits, report the concrete session-creation blocker. Continue only through an already authorized and supported execution route; otherwise ask the user to choose an available route. Do not describe an internal worker or the current assistant's executor as a separately created, user-visible platform conversation.
- When that supported creation route is available and authorized, create exactly one persistent task using the public supported creation tool. Give it the goal, relevant source context, scope, deliverables, and verification criteria. Include only information appropriate for a user-visible task conversation.
- Record the actual returned thread ID and confirmed environment selector immediately. A request accepted for execution can still be starting; record that distinction. If creation has an uncertain outcome, inspect supported task listings before any retry. Never blindly create a duplicate.
- After successful session creation, bind the already received activity to that returned thread ID only if the existing binding permits it; do not overwrite a different binding. If panel writing fails, retain the verified identity in the authorized task context and retry only the panel update; do not create another execution session.

## Track the executor and current work

- Separate three facts: the stable panel-local profile key, the executor match verified through supported tools, and the current run/work type. A profile, nickname or portrait alone never proves platform identity, permanent availability or a reusable cross-task session.
- Before registering, inspect profiles and verify the actual executor against the coordination context. Reuse a key only for that same verified executor; never merge workers because their tasks, names or avatars look similar. If the match is unavailable, keep it unknown or historical. Retain existing IDs and all assignment/history links.
- Give each genuinely new executor one distinct, pleasant fixed nickname and optional English display name; preserve them across stages. Never register task titles, role labels (such as developer/reviewer), or activity descriptions as names. Put the task on its run and the responsibility in assignment work_type.
- Use the installed agent-profile API for an authorized nickname or fixed-portrait correction. Preserve the old display label in profile history. Select one original code/vector portrait and keep it fixed; changing language or work type must not change it. A portrait is decoration, not identity verification. New automatic registrations choose an unused portrait while the 48-style catalog has capacity. Explicit selections or catalog exhaustion may repeat a style; repeated portraits never mean the same executor. Check for an unused style before an authorized manual selection.
- When agent-identity is supported, record source, verification, sanitized evidence and observation time after the actual match. observed means a manually checked match at that moment, not guaranteed future continuity. Use historical for retained records whose executor cannot be checked; never invent a platform ID or update execution status just to make a card look current. On an older version, state this provenance in the note and report the structured tracking gap.
- When a supported independent platform conversation is unavailable but work can continue in the user-authorized environment, preserve the panel activity and explicitly leave its platform binding absent. Do not invent a thread ID or substitute another environment. Use the permitted execution tools and report their actual limits.
- Associate a work type with the task assignment, such as development, research, testing or review; change it with the current work. Do not turn it into a permanent occupation or pretend an idle executor is still working.
- Record observed executor state separately from task lifecycle. Show idle when its turn finishes; a larger project can remain unfinished. Preserve unfinished assignments and recent completed activities separately.
- Keep user-facing summaries and optional English descriptions factual. Keep original task titles and source text unless an explicit translated variant exists. Never copy internal worker transcripts or identifiers into the panel.

## Archive every task deliverable

Read [references/task-files.md](references/task-files.md) before producing reports, images or other user-facing files. Resolve the existing task and its private folder first; use the same folder for every stage. Verify each deliverable, register it through the installed panel's supported file command, and confirm that its task file list contains it before claiming it is archived. A temporary file or a chat message alone is not a registered deliverable. Preserve Library identity and use the current Library workflow when delivery in chat requires an attachment.

## Keep the timeline accurate

At meaningful milestones, refresh the actual executor observation and record the result on its existing goal/run. Do not wait until delivery to register work. When the worker ends, inspect its outcome, record idle separately, and keep the task open if approval, an external result or unfinished scope remains. Parent coordination remains responsible for goal-level closeout. Never treat the latest completed run as proof that all parallel runs are complete.


Read [references/tool-contract.md](references/tool-contract.md) before binding or ingesting events. Configure the installed panel CLI and its private data directory explicitly; do not guess account paths, URLs, session IDs, or credentials.

- Group all stage updates under the same activity binding. Verify that observed events belong to the bound session before importing them.
- Import only incremental, user-facing facts: requested scope, meaningful progress, decisions, test results, blockers, and delivered outcomes. Exclude raw transcripts, private instructions, hidden reasoning, private operational notes, credentials, and unrelated personal information.
- Use a stable source event ID from the verified source. If the source provides no event ID, derive a deterministic ID from the verified thread ID, source timestamp, and sanitized event content, and identify it as derived. Never generate a new random ID when retrying the same event.
- Label observation time, source, environment, and manual synchronization accurately. A bound session is not proof of a live connection. Show last observed state and freshness; use unknown when state cannot be checked.
- Record terminal status only after reading evidence of the actual outcome. Distinguish completed work from failed, interrupted, disconnected, or waiting-for-approval work. A running task remains open until the user's completion condition is met or a real blocker requires their input.
- Deliver a concise result with verified artifacts or permitted task links. Share only returned or verified URLs; omit unsupported links for the user's viewing surface. Preserve the binding for subsequent continuation.

## Recover without duplication

- On access denial, stop the denied action and report the action, target, and required permission. Do not bypass it with a different tool.
- If the executor disconnects, preserve the activity and binding, explain which unfinished work is blocked, and resume the same session when supported.
- If a thread is inaccessible or missing, do not overwrite its binding silently. Ask before an explicitly recorded replacement; preserve the original identity and history.
- If the public interface cannot create the requested kind of activity, say so. Do not invoke undocumented APIs, expose internal workers, or claim a panel entry is an independent platform session.

## Close out or wait honestly

Use [references/closeout.md](references/closeout.md) for the shared completion checklist, waiting states and optional hourly monitoring setup. Skill availability, loading for a turn, actual delegation, panel registration and automatic scheduling are separate checks. Do not promise guaranteed triggering or global enforcement. This bundled source is the authoritative project workflow; importing it into an account is a separate, explicit installation step. Do not claim account installation, loading or monitoring merely because these files exist.

## Meaningful updates while work is ongoing

Do not wait until a long task finishes to record or communicate its progress. Record a short, user-facing paragraph when a concrete step starts, produces a result, or changes the next step. Keep all these milestones in the same goal activity and current run; do not create a task for each tiny step. Distinguish the latest work result from executor heartbeat or a refreshed timestamp.

When the installed CLI supports `progress-update`, use it for the current step, result, next step and evidence without forcing a lifecycle transition from running to running. An unchanged milestone is not a new event. Use a stable source event ID for retry safety. Only provide completed/total/unit when a real tool or process measured those values. For long renders with observable counts, check at a bounded 30–60 second cadence and record only changed counts or a meaningful result; do not fabricate percentages or continuously append heartbeat text.

Refresh actual participant observations at meaningful milestones. Keep primary ownership intact and retain assigned participant identities for their respective runs after observations become old. Show observation time and stale/unconfirmed state separately; an old waiting-run participant must not become the current run’s executor merely to fill a card. An old running observation is not proof that execution continues. User-facing paragraphs may describe outcomes and next steps, never private reasoning, raw tool transcripts or internal worker identities. Source availability and account Skill installation remain separate; this instruction does not guarantee automatic invocation or schedule a monitor.
