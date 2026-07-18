<!-- historical: production hostnames/IPs in this file are session records; see docs/architecture/multi-site-topology.md §4.1 for current example names -->

# Handsets vs uiautomator2 vs raw dump — live bench

Date: 2026-07-09. Hosts: **s24** + **hd8**. Stay-awake held. Drivers run
serially (UiAutomation exclusive — kill the other between blocks).

Script: [`bench_handsets_vs_u2.py`](bench_handsets_vs_u2.py).

## Results

### s24 (`adb-RFCX219CHKA-…` / AutoJs6 a11y ON)

| Scenario          | Raw dump       | Handsets          | uiautomator2  |
| ----------------- | -------------- | ----------------- | ------------- |
| Hierarchy (ms)    | p50=**2496**   | p50=**60**        | p50=**263**   |
| Settings find+tap | p50=2680 (5/5) | p50=**365** (5/5) | p50=641 (5/5) |
| Driver start (ms) | 0              | 1012              | 1471          |

Hierarchy: Handsets **~42×** faster than raw, **~4.4×** faster than u2.
Settings find+tap: Handsets **~7×** faster than raw, **~1.8×** faster than u2.

### hd8 (USB `GN43T503430603PS` / AutoJs6 a11y ON)

| Scenario          | Raw dump                              | Handsets              | uiautomator2                                        |
| ----------------- | ------------------------------------- | --------------------- | --------------------------------------------------- |
| Hierarchy (ms)    | p50=**596**                           | p50=**35**            | **FAIL**                                            |
| Settings find+tap | p50=679 (**0/5** — Fire label/layout) | p50=**196** (**5/5**) | n/a                                                 |
| Driver start (ms) | 0                                     | 329                   | `ERR:BAD_ARG:bad-length` (leftover protocol / slot) |

Hierarchy: Handsets **~17×** faster than raw. u2 failed to connect cleanly after
Handsets teardown on Fire (exclusive UiAutomation + binary protocol glitch).

### AutoJs6 drawer note

Initial bench reported 0/3 for drawer on both drivers due to a **script timing
bug** (force-stop + immediate open without waiting for hamburger). Manual
recheck the same day: Handsets `switch_near_label("Shizuku access")` →
`(True, True)` on **s24 and hd8** with a11y ON. Production
`enable_autojs6_shizuku.py` already green on all three hosts.

## Verdict

**Adopt Handsets as the primary Mac fleet UI driver.**

| Criterion                  | Winner                                    |
| -------------------------- | ----------------------------------------- |
| Hierarchy latency          | Handsets (17–42× vs raw; ~4× vs u2)       |
| Settings find+tap          | Handsets (faster + Fire reliability)      |
| Coexists with AutoJs6 a11y | Handsets (proven); u2 fights UiAutomation |
| Multi-device               | Handsets via fixed ports (9012/9013/9014) |
| On-device Termux scripts   | Raw dump only (no Mac `hs` forward)       |

**Keep:** raw `uiautomator dump` as fallback when Handsets unavailable.
**Optional:** uiautomator2 for one-off Mac debugging — **never** concurrent with Handsets.
