# stayturgid Auto Update

Automatic update notifications for the stayturgid Tasker project, based on
[Task Auto Update](https://taskernet.com/shares/?user=AS35m8n7%2B%2FhaeKBj3hNzHKtnU27LX%2BE4bd60KiPGki8mGxMAzSIDZAELwOTVhQxZ25YrHYlft5k%3D&id=Task%3ATask+Auto+Update)
by Joker (u/Bushido---), adapted for **GitHub-only** version detection.

## Files

| File | Purpose |
|------|---------|
| `stayturgid_update_check.tsk.xml` | Pre-configured for stayturgid — **use this one** |
| `Task_Auto_Update.tsk.xml` | Original unmodified download from TaskerNet (reference) |
| `../../version.json` | Canonical published version + changelog (fetched by devices) |

## How it works

`stayturgid_Update_Check` is a Tasker task that:

1. Fetches `version.json` from GitHub raw (`version_check_url` in `act6`)
2. Regex-extracts `"version": "..."` from the JSON response
3. Compares that to the locally installed version (also in `act6`)
4. If GitHub has a newer version, posts a notification with **Update** / **Skip**
5. **Update** downloads the task XML from GitHub and runs the AutoInput import-dialog sequence
6. Supports English, German, French, Russian, Turkish, and Chinese UI strings

**No TaskerNet dependency** for version detection or download — only GitHub.

## Installation

### 1. Import the task (or full project)

The task is embedded in `tasker/stayturgid.prj.xml` (task id 26). Prefer importing the
full project via `tasker-io` (see `tasker-io/README.md`).

Standalone task import:

```bash
adb push tasker/auto-update/stayturgid_update_check.tsk.xml /sdcard/Tasker/stayturgid_update_check.tsk.xml
```

Then in Tasker: **+** → **Import Task** → select the file.

### 2. Daily trigger profile

`stayturgid.prj.xml` includes **Daily_Update_Check** — Time 10:00–10:01 daily →
`stayturgid_Update_Check`. Re-import the project to get it on device.

## Releasing an update

1. Make changes and test on device.
2. Export project from Tasker → commit `tasker/stayturgid.prj.xml`.
3. Bump **both**:
   - `version.json` at repo root (`version` + `changelog`)
   - `act6` in `stayturgid_update_check.tsk.xml` (and embedded copy in `stayturgid.prj.xml`) — same `version` + `changelog`
4. `git push` to `master` — devices detect on next daily check.

```bash
# Verify version.json is live:
curl -sS https://raw.githubusercontent.com/djbclark/stayturgid/master/version.json
```

TaskerNet republish is **optional** (for human discovery only); auto-update does not use it.

## Two-call design

- **First call** (no parameters): full version-check flow
- **Callbacks** (`%par1=user_input`, `%par2=update|skip`): jump to Update or Skip block

Use **TestUpdateTrigger** on device to force the update path without bumping `version.json`.
