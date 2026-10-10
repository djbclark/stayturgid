# fdroid_install

> **Archived 2026-10-09.** The `stayturgid.fdroid` collection this module belonged to
> was deleted on 2026-07-30 ([#119](https://github.com/djbclark/stayturgid/issues/119)).
> Fleet apps now come from the checksummed `android_common.bootstrap_apks` lock.

FQCN: `stayturgid.fdroid.fdroid_install`

Install an F-Droid app on a connected device via `fdroidcl install`.

## Parameters

| Parameter | Description                                          |
| --------- | ---------------------------------------------------- |
| `device`  | ADB serial or fleet alias (resolved on control node) |
| `package` | F-Droid application id                               |
| `force`   | Run fdroidcl even when package already installed     |

## Example

```yaml
- stayturgid.fdroid.fdroid_install:
    device: "{{ adb_target }}"
    package: org.breezyweather
  delegate_to: localhost
```

Used by `stayturgid.android_common.ensure_apps` when `source: fdroid`.
