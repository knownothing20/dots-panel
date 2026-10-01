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
2. Inspect the configured panel's existing activities and bindings before creating anything. Read the bound session through a supported tool and compare its purpose and latest state with the request. Reuse a matching activity, including a completed activity reopened for the same work. Ask one concise question if several bindings could match or the scope is ambiguous.
3. Treat a genuinely separate goal or an explicit request for a separate activity as a new activity. Creating a panel record alone does not create a real execution session.
4. Read the current supported environment and task-tool descriptions. Use [references/tool-contract.md](references/tool-contract.md) for the verified baseline and failure handling. Respect the user's chosen environment and cost constraints. Do not substitute a computer or executor without authorization.

## Delegate and register before long work

For a new development, research or deliverable goal, briefly acknowledge the outcome and delegate through an actually available supported execution tool. In the assistant's authorized cloud environment, use a real native worker when supported; do not require a desktop or saved environment for that route. For a user-selected desktop, Remote or saved coding environment, use its supported durable-task route. Reuse the executor for continuing the same assignment where supported. Ordinary conversation does not require a task.

Immediately after real dispatch, before lengthy implementation:
1. Reuse the matching goal activity or register a genuinely new goal, then start or continue its appropriate run. A finished run stays finished; continued work uses a new run in the same activity.
2. Register a friendly panel profile using a stable panel-local key, never a runtime path or fabricated platform thread ID. A profile records a person-readable executor observation, not an independent conversation.
3. Observe the real returned or queried state: running only after confirmed execution, unknown for pending initialization, and idle after a turn ends. Record the observation time and manual source in plain language.
4. Associate each participant with the concrete run using `agent-run-assign`. Several participants may share a run, and several runs may share an activity. Preserve an existing primary owner; do not replace it merely to display another participant.
5. Read the panel state back and verify the activity, run and participant appear. If recording fails, fix registration without dispatching duplicate workers. Tell the user about any visible tracking gap.

Keep native worker identities in the authorized coordination context only. Never copy their raw identifiers, transcripts, private instructions or hidden reasoning into panel profiles, timelines or portable source. Bind a platform conversation only when an actual persisted thread ID was returned. The absence of such a binding does not mean no work occurred.

## Create or reuse a durable session when applicable

- For an existing binding, use its actual thread ID with supported read and message tools. Continue the same session for all stages. Do not create a fresh session merely because a stage changed or another message arrived.
- For a new goal requiring a durable external execution environment, discover eligible connected computers/remotes and saved coding environments. Select only an available, authorized environment that satisfies the request. If none fits, report the concrete session-creation blocker. Continue only through an already authorized and supported execution route; otherwise ask the user to choose an available route. Do not describe an internal worker or the current assistant's executor as a separately created, user-visible platform conversation.
- When that supported creation route is available and authorized, create exactly one persistent task using the public supported creation tool. Give it the goal, relevant source context, scope, deliverables, and verification criteria. Include only information appropriate for a user-visible task conversation.
- Record the actual returned thread ID and confirmed environment selector immediately. A request accepted for execution can still be starting; record that distinction. If creation has an uncertain outcome, inspect supported task listings before any retry. Never blindly create a duplicate.
- After successful session creation, create or select the panel activity and bind it to that returned thread ID. If panel writing fails, retain the verified identity in the authorized task context and retry only the panel update; do not create another execution session.

## Track the executor and current work

- Reuse a verified executor identity for continuing work when supported. Keep the stable panel key independent of its nickname, avatar and optional English display name. A panel profile alone neither creates nor proves a live executor.
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

Refresh actual participant observations at meaningful milestones. Keep primary ownership intact while showing freshly observed running participants for the current work. An old running observation is not proof that execution continues. User-facing paragraphs may describe outcomes and next steps, never private reasoning, raw tool transcripts or internal worker identities. Source availability and account Skill installation remain separate; this instruction does not guarantee automatic invocation or schedule a monitor.
