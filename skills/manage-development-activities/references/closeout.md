# Task closeout and optional monitoring

## Before reporting completion

- Recheck the user's goal, scope and completion condition against observed results
- Run relevant validation and full project tests; distinguish passed checks from skipped, blocked or unverified checks
- Inspect changed files for private data, accidental unrelated changes and unauthorized side effects
- Register verified deliverables in the same activity's private outputs and verify their file-list entries
- Record concise results and remaining limitations on the same timeline; mark a stage verified only with evidence
- Update the verified executor's observation to idle when its turn has ended; do not confuse that with completion of the larger task
- Finish a run as succeeded only when its defined goal is met; retain bindings and history for continuation
- Deliver the result and accessible artifacts to the user; registration alone is not delivery

## Checkpoint before waiting or handoff

Save the user-facing goal and constraints, actual outcomes and deliverable references, verification and remaining limits, blocker and next step in the same activity. The coordinator owns receipt and passes the existing run ID and request ID to any replacement executor; a replacement verifies them before work. Preserve bindings and participant history, and do not reuse a worker currently occupied by a different goal. Long-term memory has no fixed guarantee; retain a useful sanitized checkpoint rather than raw conversation or hidden reasoning. An independent reviewer did not produce or edit the deliverable it reviews.

## Waiting is not completion

Waiting for approval, user input, an external result, a disconnected executor, or a future scheduled check leaves the relevant task open. State what is awaited, the latest observation and the next authorized step. Never mark a task succeeded merely to remove a running badge. A short assistant turn can end while the task remains unfinished.

The panel supports running, waiting_user, waiting_external, paused, awaiting_review and the terminal succeeded/failed/cancelled states. Use the installed transition command with a factual reason, evidence and next step for every nonterminal state; supply --from-status when possible to reject stale updates. It only records lifecycle and never pauses, resumes or cancels the actual executor. Log/heartbeat updates do not implicitly resume waiting work. Terminal runs cannot reopen; subsequent authorized work uses a new run under the same activity. On an older installed version without transition, record the waiting reason as a factual activity message and keep the run open rather than inventing unsupported state values.

Record the executor separately as idle, blocked, unavailable or unknown according to observation. A binding's observed status is a separate restricted vocabulary; use unknown when no supported value accurately represents the observation. Interrupted or failed work is not completed work. A record becoming stale does not change its lifecycle.

If the user asked to monitor an operation until it ends, keep responsibility for that outcome until the agreed stopping condition, cancellation or an approval/access blocker. Do not replace an active operation with an hourly automation merely for convenience.

## Optional hourly check, separately authorized

The panel is a recorder, not a scheduler. Its schedule-register command only stores metadata. Installing the panel or this Skill creates no automation and grants no account access.

Only when the user requests an hourly check in their own account:

1. Agree the exact task/source, hourly cadence, timezone, notification destination, useful findings to report, and stopping condition. Default to read-only checking and reporting; do not infer permission to restart, publish, purchase or message third parties
2. Verify source access through a supported read-only action. Inspect that account's supported scheduling tools; if unavailable, explain the blocker rather than creating a cron job, OS startup entry or a fabricated schedule
3. Create the explicitly requested check through the supported account scheduling interface, using its documented minimum interval and timezone behavior. Keep secrets, private transcripts and unrelated account details out of its prompt
4. Read back the actual returned task identity, enabled state and schedule. An accepted creation request is not evidence a check has run. Reconcile uncertain creation through supported listing before retrying
5. Optionally record verified schedule metadata in private DATA with the installed CLI. Label whether it is configured, enabled or last observed; never equate a local row with a live integration
6. Report configuration separately from execution. Verify the first run when available; distinguish no findings, unreadable source, failed run and delivered notification. Preserve the user's stopping condition and pause dependent work if permission or access is missing

Recipients importing this project must set up their own authorized automation. No author's automation, account link, credentials or account Skill identity is distributed. The X/Twitter reader is independent and is not bundled or required.


## Supported delivery evidence gate

For new runs, successful finish/transition/closeout all require the latest explicit closeout-record. Record the actual scope, summary, passed/failed/untested result, evidence and remaining/untested limits. Select explicitly final archived outputs with actual sent/transport-accepted evidence, or state why the authorized outcome has no file. Check the installed CLI help. Failed verification cannot be labelled success; untested first-pass deliverables must retain that qualification. Historical pre-migration runs retain compatibility without invented evidence.

Artifact archival, draft/final designation, delivery transport acceptance and user-confirmed opening are separate observations. Never record sent/accepted/open solely because artifact-add succeeded or a link exists. Record only verified observations and retain the original artifact identity; new bytes require a new version. A copyable suggestion is not a sent message. These commands record evidence and never send, open or execute an output.


## Installation acceptance

Use panel doctor for read-only source/data/schema/bundled-source checks. Report unknown account Skill or scheduler components honestly. Manual installation observations do not install a Skill or create a scheduler. Keep a user's personal environment-rule Skill personal and excluded from the public project bundle. Test normal delivery, waiting/resume and interruption/recovery in isolated synthetic DATA; preserve production tasks and source/account identities.
