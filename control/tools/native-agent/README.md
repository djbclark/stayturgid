# native-agent Mac tools

| Script                    | Purpose                                                                                               |
| ------------------------- | ----------------------------------------------------------------------------------------------------- |
| `grant_shizuku.py`        | pm grant + conditional Shizuku server restart (no longer touches `shizuku.json`)                      |
| `start_agent.py`          | headless PeerStartReceiver → HostService                                                              |
| `rollout.py`              | install APK + grant + Shizuku restart + start                                                         |
| `provision_peer.py`       | write the peer-start assignment `peer.json` (issue #61)                                               |
| `reingest_soft_health.py` | re-post `soft_health.jsonl` to OpenObserve after an outage (manual catch-up; Vector is the live path) |

```bash
python3 control/tools/native-agent/rollout.py           # all reachable
python3 control/tools/native-agent/rollout.py s24 p7a
python3 control/tools/native-agent/rollout.py --serial <serial>
just agent-rollout
```

## Fire HD (hd8) Shizuku note (historical, K1 era, 2026-07)

Fleet release17 APK ships **compressed** `librish.so`. Fire's `System.load` from
`base.apk!/lib/...` then crashes. Repackage with STORED `.so` + `resources.arsc`
before install (see session status doc). Even then, UserService may hit
`DeadObjectException` handing binder to the manager. Current hd8 Shizuku
failures are tracked in [#188](https://github.com/djbclark/stayturgid/issues/188).
