<!-- historical: production hostnames/IPs in this file are session records; see docs/architecture/multi-site-topology.md §4.1 for current example names -->

# AutoJs6 project import questions for the senior maintainer

This is a short question set for someone who knows AutoJs6 internals well enough to answer how projects are supposed to be registered, imported, and launched. The immediate problem is now more specific: once the tree is imported in the app’s expected format, AutoJs6 recognizes the project on s24, but launch behavior is noisy because LeakCanary keeps surfacing retained-object toasts and heap-dump analysis during normal use. We still need to understand the canonical registration flow and whether an existing deployed tree should appear as a real task immediately.

## What to ask

1. What is the canonical way in AutoJs6 to register an existing script tree as a project?
2. Does AutoJs6 treat `project.json` as sufficient, or does it also require an internal workspace index or database entry?
3. Why does folder import sometimes create a `?` placeholder instead of a real project entry?
4. What exact filesystem layout does AutoJs6 expect for a project root?
5. Is there a supported way to import a project tree from `/sdcard/...` without recreating it manually in the app?
6. Why does importing `main.js` alone fail on relative `./lib/...` imports, and is there a supported project-root import flow that preserves those paths?
7. Is there a supported API, deep link, or intent for opening a project directly at `main.js`?
8. Does `Stable mode` affect whether a project shows up in `Task -> Running task`, or is that unrelated?
9. Can AutoJs6 expose a project-tree import/export format that external tooling can generate?
10. Is there a supported way to make AutoJs6 recognize an already-deployed project without manual UI setup?
11. Is the built-in LeakCanary integration expected to run on normal user launches, and can it be disabled or deferred in release builds?
12. Why does opening the project sometimes surface “retained objects” / “distinct leaks” toasts and heap-dump analysis before the script’s own behavior is visible?
13. Does AutoJs6 have a supported way to run a project without triggering leak-analysis UI on every launch?

## What to propose if he is open to changes

1. Make folder import create a real project entry when the folder contains a valid `project.json`.
2. Make the app accept `project.json` in the picker, or at least stop hiding it from the chooser.
3. Add a clear error when a folder import is not recognized as a project, instead of a `?` placeholder.
4. Add an import-from-path workflow that can be driven by automation or adb.
5. Document the expected relationship between `project.json`, the project workspace, and the `Task` tab.
6. Expose a command-line or intent-based `open project` API so deployment code can launch `main.js` reliably.
7. Add a supported “register existing folder as project” action that does not duplicate files.
8. Make project recognition work cleanly for trees deployed by external tooling.
9. Move LeakCanary out of the normal user-facing startup path, or at least add a project/runtime setting to suppress it when it is not actively being debugged.
10. Make startup errors and leak-analysis status obvious in a log, not as popup/toast noise that can be confused with script output.

## Why this matters for stayturgid

Stayturgid deploys the AutoJs6 script tree from the repository, then expects `main.js` to be runnable after reboot without manual re-creation of the project inside the app. On current testing, the project can be recognized once imported in the app’s expected format, but LeakCanary adds enough noise that it is hard to tell whether `main.js` actually started. If AutoJs6 requires a different registration flow, the repo should either adapt to that flow or the app should expose a supported way to register an already-deployed project and suppress debug-only leak UI during normal use.

## Relevant local files

- `~/stayturgid/README.md`
- `~/stayturgid/docs/README.md`
- `~/stayturgid/docs/options.md`
- `~/stayturgid/docs/handoff.md`
- `~/stayturgid/docs/research/javascript-runtime-supervision-2026-07-13.md`
- `~/stayturgid/device/autojs6/main.js`
- `~/stayturgid/device/autojs6/project.json`
- `~/stayturgid/device/autojs6/scripts/boot-launcher.js`

## Relevant AutoJs6 source hints

- `~/src/AutoJs6/app/src/main/java/org/autojs/autojs/project/ProjectConfig.java`
- `~/src/AutoJs6/app/src/main/java/org/autojs/autojs/model/project/ProjectTemplate.java`
- `~/src/AutoJs6/app/src/main/java/org/autojs/autojs/ui/filechooser/FileChooserDialogBuilder.java`
- `~/src/AutoJs6/app/src/main/java/org/autojs/autojs/ui/explorer/ExplorerProjectToolbar.java`
- `~/src/AutoJs6/app/src/main/assets-app/docs/qa.html`

## Short version to paste into a conversation

> We deploy a full AutoJs6 script tree from stayturgid, but on hd8 the folder import UI only shows a `?` entry and the project does not behave like a real project unless it is created in-app. What is the canonical way to register an existing script tree as a project, and can AutoJs6 expose a supported import/open path for a deployed `project.json` tree?

> Updated after testing on s24: the imported project is recognized, but AutoJs6 keeps surfacing LeakCanary retained-object toasts and heap-dump analysis during normal launch. Is that expected, and can it be disabled, deferred, or moved out of the normal startup path so script execution is observable?
