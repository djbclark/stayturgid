# tasker-io — reliable Tasker import/export over ADB

Importing Tasker data has been the single flakiest part of this project. This sub-folder
is a self-contained, reusable toolkit for doing it **reliably**, intended to eventually be
spun out as its own project. Develop/experiment here against throwaway projects — never
against the live `stayturgid` project.

## TL;DR — how to update one task reliably

```bash
# extract a task from a project export and import/overwrite it on the device
python3 tasker_io.py <serial> wrap-task ../tasker/stayturgid.prj.xml task21 /tmp/ADB_Core_Watchdog.tsk.xml
python3 tasker_io.py <serial> import-task /tmp/ADB_Core_Watchdog.tsk.xml
```

That runs an **intent-launched, text-button-only** import — no delete-everything dance,
no coordinate guessing. Verified on Pixel 7a / Tasker 6.7.5-beta / Android 16.

## The key discovery (the robust path)

Tasker exposes an import Activity that accepts a DocumentsProvider content URI by intent
and imports a **single task with overwrite**, using only text-button dialogs:

```bash
am start -n net.dinglisch.android.taskerm/com.joaomgcd.taskerm.datashare.import.ActivityImportTaskerDataFromXml \
  -a android.intent.action.VIEW \
  -d "content://com.android.externalstorage.documents/document/primary%3ATasker%2FUpdates%2FADB_Core_Watchdog.tsk.xml" \
  -t text/xml --grant-read-uri-permission
```

- The file must live under `/sdcard/…`; the URI is `primary:` + the **URL-encoded** path
  (`Tasker/Updates/x.tsk.xml` → `primary%3ATasker%2FUpdates%2Fx.tsk.xml`).
- `--grant-read-uri-permission` + `-t text/xml` are required; without them Tasker (or the
  provider) rejects the read (the older `-d content://…` attempts failed with
  "UID 2000 does not have permission").
- Dialog chain (all **text** buttons — reliable regardless of screen size/geometry):
  1. *"Import Data — … Are you sure?"* → **YES**
  2. *"A Task with the name '…' already exists. Want to overwrite it?"* → **YES**
     (note: the button is **YES**, not "OVERWRITE")
  3. *"Run task now?"* → **NO** (unless you want to run it)
- The task keeps its `id`, so profiles that reference it stay wired up. 

This is what `tasker_io.import_task()` automates.

## Prior art (web/forum search, 2026-07-05)

- **[Taskomater/Tasker-XML-Info](https://github.com/Taskomater/Tasker-XML-Info)** — the
  canonical reference for the XML format (`.prj.xml` / `.tsk.xml` / `.prf.xml` / backup
  `.xml`; `sr` identifiers, `id`, `nme`, `mid0`/`mid1` task refs).
- **[Taskomater/tasker_config_utils](https://github.com/Taskomater/tasker_config_utils)**
  — bash utils that **only modify exported XML files, not live config**. Useful command:
  `convert_project` makes a project "non-standalone" (strips references to tasks/profiles
  not originally in it) to avoid **duplicate-name import conflicts**.
- **[Taskomater/tasker_package_utils](https://github.com/Taskomater/tasker_package_utils)**
  — package-level ops (perms, convert to system-priv) — **requires root**.
- **Conclusion: there is no clean root-free programmatic import.** Everyone routes through
  the UI or AutoInput. The intent path above is the least-fragile UI route.

## Gotchas (confirmed empirically + by prior art)

| Gotcha | Effect | Fix |
|--------|--------|-----|
| XML comments (`<!-- -->`) inside the data | import silently produces an **empty** project | strip all comments before import |
| Duplicate names | project/task import fails ("… already exists") | task import → **overwrite YES**; project import → delete the old project first, or use non-standalone export |
| File suffix must match type | import fails | `.tsk.xml` for tasks, `.prj.xml` for projects |
| "Delete **Contents**" on a project | leaves a **ghost project** → later "a project with that name already exists" | use Delete → **Keep Contents** to remove the shell, or avoid full reimport entirely (prefer task import) |
| Selection-mode top-bar icons (trash/export) | **x-position shifts with selection count** → coordinate taps hit the wrong icon | find by `content-desc`, never hardcode x (`_tap_topbar_action`) |
| Tasker left in the task editor / a context menu | next automation step targets the wrong screen | always call `goto_main()` first |
| Tasker's terminal/list custom views | uiautomator can't always read row text | prefer text-button dialogs (import path) over list scraping |

## When you still need a full-project reimport

Task import can't add/remove profiles or restructure a project. For that, the fallback is
the full dance: delete profiles (they reference tasks) → delete tasks (handle
"used in other tasks" → DELETE ANYWAY) → delete project shell (Delete → **Keep Contents**)
→ long-press a project tab → Import Project → pick the file → YES/YES. Do it with
`goto_main()` between steps and `_tap_topbar_action()` for the trash icon. This remains the
fragile path — minimize its use by keeping structure stable and updating tasks via
`import_task()`.

## TODO / ideas to make this its own project

- Wrap the full-project reimport into a tested `reimport_project()` with the robust primitives.
- Add `export_task`/`export_project` (drive the UI "Export → XML to Storage", then pull).
- Port `convert_project` (non-standalone) so multi-project configs import without conflicts.
- Optional: an on-device Termux variant using the same intent (Tasker's own auto-update
  task already does this with AutoInput for the taps).
