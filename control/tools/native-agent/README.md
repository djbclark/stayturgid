# native-agent Mac tools

| Script             | Purpose                                       |
| ------------------ | --------------------------------------------- |
| `grant_shizuku.py` | pm grant + patch `shizuku.json`               |
| `start_agent.py`   | force-stop + MainActivity → HostService       |
| `rollout.py`       | install APK + grant + Shizuku restart + start |

```bash
python3 control/tools/native-agent/rollout.py           # all reachable
python3 control/tools/native-agent/rollout.py s24 p7a
python3 control/tools/native-agent/rollout.py --serial GN43T503430603PS
just agent-rollout
```

## Fire HD (hd8) Shizuku note

Fleet release17 APK ships **compressed** `librish.so`. Fire's `System.load` from
`base.apk!/lib/...` then crashes. Repackage with STORED `.so` + `resources.arsc`
before install (see session status doc). Even then, UserService may hit
`DeadObjectException` handing binder to the manager — track under K1 remaining work.
