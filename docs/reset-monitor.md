# Reset observations and the local directory monitor

The optional panel companion observes explicitly configured directory identities.
It does not prove a cloud machine reset, scan file contents or guarantee the
host keeps it running. It records present/missing transitions, device/inode
changes, read errors, clock rollback and intervals without samples. Historical
estimates must name their evidence and remain distinct from fresh observations.
All event times are stored as UTC epochs and displayed in UTC and Asia/Shanghai.
A planned execution time is not an actual observation time. UTC is a reference
time zone, not a claim about an OpenAI service's local time.

## Explicit initialization and execution

Choose a private monitor state directory outside every monitored root. Use
confirmed paths in the commands below; these are placeholders. Initialization
requires a fresh directory and does not start a process or initialize panel data.

```sh
PYTHONPATH="$SOURCE/src" python3 -m dots_panel.reset_monitor init \
  --state "$MONITOR_STATE" --interval 60 \
  --path workspace="$MONITORED_ROOT" --path source="$SOURCE" \
  --path data="$DATA" --panel-data "$DATA" \
  --expected-panel-identity "$VERIFIED_INSTALLATION_ID"
PYTHONPATH="$SOURCE/src" python3 -m dots_panel.reset_monitor once --state "$MONITOR_STATE"
PYTHONPATH="$SOURCE/src" python3 -m dots_panel.reset_monitor run --state "$MONITOR_STATE"
```

Before configuring automatic imports, explicitly verify the selected panel's
installation identity against its authorized recovery/installation evidence and
record a binding with `reset-bind --expected-identity "$VERIFIED_INSTALLATION_ID"
--evidence "$VERIFICATION_EVIDENCE"`. A missing or different identity blocks
imports; a matching table name alone is insufficient. The monitor checks both
the existing identity file and the database's immutable explicit binding.
Unknown databases are not auto-bound. File descriptors remain held while
connections are opened; identity/path replacement is checked before writing.

The foreground run samples on an approximately 60-second monotonic cadence and
stops on normal Ctrl+C/SIGTERM. It does not install an OS service, auto-start,
platform schedule, credential or network endpoint. Only the running process's
own verified identity may be used to stop it; do not terminate by fuzzy name.
Use `export --state "$MONITOR_STATE"` for a JSON export of recorded events.
Do not put that output, the state database or real path configuration in GitHub.

The independent SQLite journal commits samples and events transactionally.
Event IDs are stable when exporting/importing again. An existing compatible
panel database can receive these events idempotently. Missing panel data is a
recorded import limitation, never a reason to initialize an empty replacement.
The panel must already have its reset schema, so an old version is reported
unavailable rather than silently migrated by the monitor.

Directories are opened component by component without following symlinks;
there is no recursive traversal. Only configured labels and directory identity
metadata are events. The private configuration retains selected paths.
If the monitor state disappears or changes identity while the process runs,
the process stops rather than recreating continuity. If the monitor and its
journal disappear together, the time and intervening events are unknown.
A local journal alone is not an off-computer backup.

## Scheduling boundaries

A local minute observer and a platform schedule are separate components.
Create or change a platform task only with explicit user authorization and the
current platform tools. A platform limit must not be presented as a successfully
created one-minute schedule. A separately authorized ten-minute backup/source
check and hourly task audit retain independent configuration and execution
observations. Installing this source creates none of those schedules.

## Recovery and evidence

An event bounded by last-present and first-missing observations narrows an
interval; it is not an exact reset timestamp. A directory replacement or remount
can change device/inode without a whole-machine reset. Never infer a daily reset
schedule from two gaps. Persist source references for estimates and do not fill
missing samples retrospectively. Panel event history is append-only through the
supported APIs and cannot close a task or resume an executor.
