# stayturgid Auto Update

Automatic update notifications for the stayturgid Tasker project, powered by
[Task Auto Update](https://taskernet.com/shares/?user=AS35m8n7%2B%2FhaeKBj3hNzHKtnU27LX%2BE4bd60KiPGki8mGxMAzSIDZAELwOTVhQxZ25YrHYlft5k%3D&id=Task%3ATask+Auto+Update)
by Joker (u/Bushido---).

## Files

| File | Purpose |
|------|---------|
| `stayturgid_update_check.tsk.xml` | Pre-configured for stayturgid — **use this one** |
| `Task_Auto_Update.tsk.xml` | Original unmodified download from TaskerNet (reference) |

## How it works

`stayturgid_Update_Check` is a Tasker task that:

1. Fetches the stayturgid project XML from TaskerNet via its undocumented API
2. Regex-extracts the `"version": "..."` string embedded in `act6`'s JavaScript
3. Compares that to the locally installed version (also in `act6`)
4. If TaskerNet has a newer version, posts a notification with two buttons:
   - **Update** → opens the TaskerNet import link directly in Tasker
   - **Skip** → dismisses the notification
5. Supports English, German, French, Russian, Turkish, and Chinese UI strings

The version is embedded in `act6`'s JavaScript (`updaterData[0].version`). When you
bump that string and republish the project to TaskerNet, all installed copies
will detect the mismatch on their next check.

## How version detection works

The mechanism uses a clever self-referential trick:

1. The task fetches `https://taskernet.com/_ah/api/datashare/v1/sharedata/<user>/<id>?a=0&xml=true`
2. The TaskerNet API returns JSON with a `shareData` field containing the raw XML
3. The task runs a regex on that JSON looking for `"version": "1.x"`
4. Because `act6`'s JavaScript is embedded verbatim inside the XML (which is inside the JSON),
   the regex finds the version string directly in the response body
5. No custom server, no separate metadata endpoint needed

## Installation

### 1. Import the task into Tasker

Copy `stayturgid_update_check.tsk.xml` to `/sdcard/Tasker/` on the device, then in
Tasker: **+** → **Import Task** → select `stayturgid_update_check`.

Alternatively, push it and import via ADB:

```bash
adb push tasker/auto-update/stayturgid_update_check.tsk.xml /sdcard/Tasker/stayturgid_update_check.tsk.xml
```

Then in Tasker import from `/sdcard/Tasker/stayturgid_update_check.tsk.xml`.

### 2. Add a trigger profile

The task doesn't run automatically on its own — you need a Tasker profile to
trigger it. Recommended options:

**Daily check (new profile):**
- Profile → Time → 10:00 → Every day
- Task → `stayturgid_Update_Check`

**On-demand (shortcut):**
- Profile → Event → UI → Shortcut
- Task → `stayturgid_Update_Check`

**Piggyback on boot (add to existing boot task):**
Add a "Perform Task" action at the end of `ADB_Core_Watchdog` calling
`stayturgid_Update_Check` — but this will check on every 20-minute interval,
which is noisy. A separate daily profile is cleaner.

## Releasing an update

When you make changes to the stayturgid project and want to notify users:

1. Open `stayturgid_update_check.tsk.xml` (or the task in Tasker)
2. In `act6`, bump `"version": "1.0"` to the new version (e.g., `"1.1"`)
3. Update `"changelog"` with what changed
4. Export the full stayturgid project from Tasker → share to TaskerNet
   (overwrite/update the existing share — same URL, no link changes needed)
5. Done. Installed copies will detect the version bump on their next check

The TaskerNet URL never changes when you update an existing share, so the
`taskernet_url` in `act6` stays the same forever.

## Two-call design

The task uses a two-call pattern for notification button actions:

- **First call** (no parameters): runs the full check flow
- **Subsequent calls** (`%par1=user_input`, `%par2=update|skip`): jump straight
  to the Update or Skip action block

The notification buttons trigger "Perform Task → stayturgid_Update_Check" with
those parameters, which is how Tasker handles notification button callbacks.

## Customization

All user-visible strings in `act8` can be extended with additional languages
by adding entries to the `translations` object.

The notification channel is `stayturgid` (matching the main project's channel).
