# Checkpoint — resume p7a AutoJs6 drawer (H3 follow-up)

**Saved:** 2026-07-09 ~13:02 EDT  
**Host:** p7a (Pixel 7a)  
**Why paused:** Operator needed the phone back within 3 minutes.

## Done on p7a this session

- Fleet Ansible pass largely applied (Termux userland, SSH mesh known_hosts fix
  landed mid-run, F-Droid/Play roles, app privileges).
- Obtainium catalog import: **OK**
- Aurora first-run setup: **OK**
- Shizuku grant for AutoJs6: **started** — log shows
  `Shizuku: allowed AutoJs6 (uid=10592)` then interrupted during drawer UI.
- Screen control / inversion: **cleared** (presence off, inv=0, home launcher).
- Freed at checkpoint: inv=0, focus=bitpit HomeActivity, presence OFF.

## Not done on p7a

- `./autojs6/mac/enable_autojs6_shizuku.py p7a` — finish drawer defaults +
  Shizuku access verify.

## Resume command (screen unlocked)

```bash
cd /Users/djbclark/stayturgid
# optional: agent may enable stay-awake while working
adb -s 100.65.230.108:5555 shell svc power stayon true
adb -s 100.65.230.108:5555 shell settings put global stay_on_while_plugged_in 7
./autojs6/mac/enable_autojs6_shizuku.py p7a
```

## Sibling status at pause

- **s24:** AutoJs6 drawer + Shizuku OK; project redeployed (clean lib/).
- **hd8:** AutoJs6 + Shizuku probe `operational=true`; Shizuku start via
  `LD_LIBRARY_PATH=…/lib/arm64 libshizuku.so`; presence uses
  `STAYTURGID_NO_LOCAL_ADB=1`; Mac enable skips `request-screen`.

## Related fixes in tree

- `autojs6/mac/deploy.py`: wipe + push dir (not `dir/.` into empty) + verify
- `known_hosts_mesh.j2`: `hostname keytype base64` for ansible.builtin.known_hosts
- Play metronome canary: `host_vars/s24.yml` only
- `MAC_ADB_PRIV_ALIASES` / Fire presence: no localhost:5555 hang

## Do not

- Re-run full `deploy_fleet.py` just to finish p7a drawer.
- Touch p7a until operator says it is available again.
