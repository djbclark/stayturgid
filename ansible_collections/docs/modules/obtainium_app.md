# obtainium_app

**FQCN:** `stayturgid.obtainium.obtainium_app`  
**Runs on:** device (Termux over SSH)

Renders Obtainium bulk-import JSON from terse app specs. Does **not** apply the
catalog — use Mac `obtainium/mac/import_catalog.py` (`obtainium://apps/` deep link).

## Example

```yaml
- stayturgid.obtainium.obtainium_app:
    apps:
      - id: org.autojs.autojs6
        url: https://github.com/SuperMonster003/AutoJs6
        name: AutoJs6
    catalog_path: /sdcard/Download/my-catalog.json
    import_ui: false
```

## Role

`stayturgid.obtainium.obtainium_apps` role
