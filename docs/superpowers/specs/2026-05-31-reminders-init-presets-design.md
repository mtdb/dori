# Reminders Init Presets Design

## Goal

Make `dori init` produce a useful reminders setup from day one while preserving
the current editable-template workflow.

The first iteration only covers the `reminders` skill. Calendar and other skills
remain out of scope, but the design should make future configurable skills
straightforward to add.

## User Experience

`dori init` remains a first-run command. It creates `~/.dori` and copies missing
runtime files from the bundled boilerplate without overwriting existing user
files.

When both `~/.dori/scripts/reminders.py` and `~/.dori/skills/reminders.md` are
missing, `dori init` asks the user to choose a reminders backend:

```text
Choose reminders backend:
  1. D-Bus desktop notifications
  2. Template script
```

The options behave as follows:

- `D-Bus desktop notifications` installs a functional Linux desktop reminders
  implementation.
- `Template script` installs the current deterministic placeholder script and
  skill guidance, intended for users who want to edit the script by hand later
  for custom behavior such as email delivery.

If only one reminders destination is missing, `dori init` installs the template
version for the missing file and leaves the existing file intact. It does not
ask the backend question because there is no safe way to infer whether the
existing script and skill markdown should be paired with a new backend. This
preserves the current "copy missing files only" contract and keeps
update/migration behavior out of scope for this feature.

## Boilerplate Layout

Reminders becomes an init preset instead of a generically copied boilerplate
script.

```text
boilerplate/
  scripts/
    analyze-folder.py
    commit.py
    docker.py
    news.py
    web.py
  skills/
    analyze-folder.md
    calendar.md
    search/
    devtools/
  presets/
    reminders/
      template.py
      template.md
      dbus.py
      dbus.md
```

The generic copy step excludes `scripts/reminders.py` and `skills/reminders.md`.
Instead, `dori init` resolves the chosen preset and copies:

```text
boilerplate/presets/reminders/<choice>.py -> ~/.dori/scripts/reminders.py
boilerplate/presets/reminders/<choice>.md -> ~/.dori/skills/reminders.md
```

The runtime contract does not change. Dori still loads skills from
`~/.dori/skills` and runs `~/.dori/scripts/<skill>.py`.

## D-Bus Reminder Behavior

The D-Bus preset uses only Python standard library code plus common desktop
commands. It does not add package dependencies.

The script:

- reads the JSON payload from `sys.argv[1]`;
- requires the existing `message` and `when` fields;
- parses simple relative expressions:
  - `in N seconds`
  - `in N minutes`
  - `in N hours`
- schedules a detached process that sleeps for the parsed duration and then
  runs `notify-send`;
- prints a clear success message after scheduling.

Failure behavior:

- missing JSON payload exits non-zero and writes `Error: Missing JSON payload`
  to stderr, matching the existing script convention;
- invalid JSON exits non-zero with a reminders-specific invalid payload message;
- missing `notify-send` exits non-zero with a clear D-Bus dependency message;
- unsupported `when` expressions exit non-zero and ask for one of the supported
  relative formats.

The D-Bus preset does not attempt natural-language date parsing, absolute date
scheduling, recurrence, persistence across reboot, or calendar integration.

## Template Reminder Behavior

The template preset preserves the current behavior:

- parse the JSON payload;
- read `message` and `when`;
- print a deterministic scheduling confirmation;
- perform no external side effects.

This option is intentionally explicit in the questionnaire. It is for users who
prefer to customize `~/.dori/scripts/reminders.py` manually after initialization.

## Skill Markdown

The selected preset controls both the script and the skill markdown.

The template markdown keeps the current broad guidance for reminders.

The D-Bus markdown keeps the same intent and payload shape but adds guidance to
prefer supported relative times such as `in 20 minutes`, `in 2 hours`, or
`in 30 seconds`. This reduces avoidable script failures by aligning model output
with what the installed backend can execute.

## Code Changes

The implementation should stay localized to onboarding:

- add a preset resolver for configurable boilerplate files;
- update `init_workspace()` to call that resolver for reminders;
- keep the existing copy-missing-files behavior for all non-configurable files;
- avoid changes to `ConversationEngine`, `run_skill()`, and the Pydantic
  reminders schema.

The prompt implementation can use Rich or standard input, but the selection
logic should be factored so tests can run without interactive input.

## Tests

Add focused tests for:

- selecting `template` installs `template.py` and `template.md` to the standard
  reminders destinations;
- selecting `dbus` installs `dbus.py` and `dbus.md` to the standard reminders
  destinations;
- existing reminders files are not overwritten and do not trigger selection;
- the template script preserves the current output behavior;
- the D-Bus script handles missing payloads, invalid JSON, supported relative
  times, unsupported times, and missing `notify-send`;
- generic boilerplate copy still installs the rest of the scripts and skills.

Tests for D-Bus scheduling should not deliver real notifications. They should
exercise parsing and subprocess boundaries with mocks or an internal dry-run
path.

## Non-Goals

- `dori update` or migrations for existing installations.
- Calendar backend selection.
- Email, webhooks, cron, systemd timers, or other reminder providers.
- Full natural-language date parsing.
- Persisting reminders across reboot.
- Changing the runtime skill execution contract.

## Open Decisions Closed

- Start with reminders only.
- Offer exactly two first backends: D-Bus and template.
- Preserve existing files during init.
- Treat template as an explicit user choice, not an invisible fallback.
- Keep future provider updates out of scope.
