# stayturgid 2.0 — pre-mortem and scope realism

- **Date:** 2026-08-08
- **Lens:** sceptical engineering manager
- **Basis:** architecture final, trust red-team, tooling reviews, ideas dump,
  live ~/ops state, open issues, and the 2026-08-06 worktree incident.

## Bottom line

This is not one eight-phase migration. It is (1) a Mac/Linux substrate
experiment, (2) a multi-host observability migration blocked on buying and
operating Linux, and (3) a secure-update plus privileged Android consent
product. Calling them one project is how it becomes permanently 80% complete.

The stated program is **210–400 operator-days with AI assistance**: about
10–20 focused months at half-time before ordinary incidents and other
projects. Secure pull plus consent alone is **95–200 days**. It is not a
Phase 5 manifest task followed by a Phase 6 UI task.

For the next 90 days, keep only current reliability work, a descriptive
Phase 0, automated worktree-provenance checks, and at most a build-only Nix
proof. Do not start pull convergence, consent, role failover, a cache, or
Free Sysadmin extraction.

## 1. Pre-mortem: February 2027 autopsy

| Rank | Probability | What happened                                                                                                                                                                                                                                                                                                 | Operational cost                                                                                                                              |
| ---- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| 1    | Very high   | The operator completed the interesting design and flake skeleton, then lost interest when the work became launchd census, test repair, secret delivery, and seven-day soaks. The Site Model describes reality but does not operate it.                                                                        | Every incident needs both the real inventory/registries and an aspirational model. Agents update whichever is easier.                         |
| 2    | Very high   | Production work kept winning: hd8 still cannot reach CLOSED_NO_SHELL because Shizuku never starts after reboot; the OpenObserve clean-log acceptance and service-restart behaviour remain unfinished. These touch the laptop, APK, and adapters that the migration needs stable.                              | Stale migration branches and new fleet regressions. Architecture work makes the working system harder to change.                              |
| 3    | High        | Mac ownership stopped half-way: Nix owns some packages and shell state, Homebrew owns others, Ansible owns services, and writer rules have exceptions. A macOS upgrade or an agent changes a dependency through the wrong writer.                                                                             | Rolling back a Nix generation does not undo Ansible, Homebrew, secrets, or mutable service state. Recovery begins with ownership archaeology. |
| 4    | High        | vps-primary remained offline_unprovisioned, as does the Intel mini. Phase 3 Linux twins, Phase 4 NixOS, moving obs-main, and a meaningful exit drill never ran.                                                                                                                                               | The sleeping M1 Air remains the sole control node and observability host. Linux code stays dead code while planning grows.                    |
| 5    | High        | Phase 5 was treated as release-tool work. It stalled on the red-team requirements: threshold root/recovery, replay protection, durable client state, typed effect IR, executor enforcement, source provenance, secret authorization, and hostile-mirror tests.                                                | A disabled partial pull agent, or worse, an enabled one-key fleet root.                                                                       |
| 6    | High        | The exit drill was deferred until after “real migration.” The Ubuntu runbook was never exercised against current inventory and adapters.                                                                                                                                                                      | The claimed escape hatch is untested prose and cannot justify further Nix investment.                                                         |
| 7    | Medium-high | AI agents rapidly created plausible systemd twins, mappings, release helpers, and lints. One carried a production-only assumption or unintended privilege path. The 2026-08-06 incident is the small version: Hermes committed into Claude's worktree; Claude merged 231 unreviewed lines under the wrong PR. | A believable bad change reaches a signed release. Automation increases review demand rather than removing it.                                 |
| 8    | Medium      | A macOS, Determinate, or nix-darwin update failed during the Mac switch. The same laptop was control node, dashboard host, release workstation, and repair environment.                                                                                                                                       | A host-management experiment impaired the tool used to repair the fleet; recovery was manual and the migration was abandoned.                 |
| 9    | Medium      | Consent shipped before executor enforcement and Android provenance. It displayed a plan, accepted a tap, then applied an opaque Shizuku-capable APK or broad recovery bundle.                                                                                                                                 | New “safety” machinery became the path that authorized persistence or exfiltration.                                                           |
| 10   | Medium      | A role mesh grew before a second live host. YAML primary/backup ordering became pseudo-HA; a partition made two actors think they could act.                                                                                                                                                                  | Split-brain release, secret, or observability state, followed by manual SSH and the old control-node model.                                   |

### The half-migrated state to avoid

The dangerous state is not “Nix failed.” It is a still-single-laptop production
system where the operator must reason about Nix generations, Homebrew, Ansible
adapters, mise, just, Site Model data, and a planned pull agent. Each has a
different rollback story.

A concrete bad month: an Ansible-rendered Vector/OpenObserve change needs an
explicit restart because its plist did not change (the current #224 class of
problem), while its package moved in a Nix generation after a Mac update. The
operator cannot know whether to roll back Nix, invoke site-serverapps, cut an
ops release rollback, or manually restart. None is a general undo. Do not
create this intermediate state merely to demonstrate progress.

## 2. Effort reality check

Operator-days include review, live proof, breakage, and documentation. AI can
generate scaffolding, tests, and repetitive adapters; it does not eliminate
human decisions, key custody, hardware work, or live acceptance. Ranges exclude
waiting for hardware, soaks, provider procurement, and unrelated incidents.

| Work                                  |                  Honest range | Why this is not a bullet point                                                                                                                                 | Scarce human attention                                        |
| ------------------------------------- | ----------------------------: | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| Reliability debt before 2.0           |                    10–25 days | #43/#188 Fire OS boot recovery, remaining peer-start E2E, #224, and OpenObserve acceptance are production work.                                                | Decide acceptable degradation; run and judge reboots/soaks.   |
| Phase 0 — map and fence               |                     5–10 days | Schema syntax is cheap; a truthful public/site/private ownership census is not.                                                                                | Decide actual writer boundaries.                              |
| Phase 1 — toolchains/build-only flake |                      4–9 days | Evaluation is easy; pinning, CI, clean recovery, and preserving toolchains are not.                                                                            | Decide what deserves pinning; review inputs.                  |
| Phase 2 — Mac substrate switch        |                    12–25 days | Services untouched does not remove package ownership, shell, upgrade, and rollback risk on the only critical laptop.                                           | Schedule recovery window; test and judge rollback.            |
| Phase 3 — role parameterization       |                    15–35 days | This is an audit of every “the Mac” assumption, not a YAML field. Each Linux twin needs proof or an explicit darwin-only decision.                             | Classify semantics and portability.                           |
| Phase 4 — first NixOS VPS             | 15–30 days after provisioning | Provider security, Tailscale/DNS policy, bootstrap, monitoring, systemd adapters, and a seven-day shadow soak precede moving observability.                    | Procure host; control credentials; promote or roll back.      |
| Phase 5 — safe pull/release-plan v1   |                   60–120 days | It is a secure-update system: threshold root/recovery, anti-replay, typed IR, executor, clean provenance, SecretSpec authorization, limits, adversarial tests. | Key ceremony, recovery/downgrade policy, authority decisions. |
| Phase 6 — consent v1                  |      35–80 days after Phase 5 | A UI is trivial beside device-bound expiring grants, enforced capabilities, receipt privacy, Android provenance, and rollback proof.                           | Define consent; review UX/privacy; test real devices.         |
| Phase 7 — exit drill                  |                     5–12 days | It needs a clean host, real inventory, induced failure, teardown, and evidence—not a one-time install.                                                         | Decide whether it works without Nix knowledge.                |
| Phase 8 — builder/cache/freeops       |                    25–60 days | A trusted cache and APK lane are supply-chain operations; public extraction is release/support work.                                                           | Operate keys/revocation; decide when two consumers exist.     |

Even allowing overlap, the complete plan is **210–400 days**. The trust and
consent program is **95–200 days** and must not start without a concrete
unattended-update requirement or real second participant.

AI cannot certify live Android recovery, choose threshold custody, make a
provider account safe, decide consent semantics, or prove a plausible
Ansible/Nix diff matches intent. In those areas AI savings become later review.

## 3. What to cut

### Keep for the next 90 days

1. **Finish reliability first.** Close or explicitly park the hd8 boot-path
   failure, OpenObserve acceptance, and restart behaviour. Do not change their
   substrate while a soak is active.
2. **Do descriptive Phase 0 only.** Add a truthful census/schema and
   one-writer lint that creates no runtime writer or generator.
3. **Automate the lesson already paid for.** A deterministic worktree-owner
   and pre-merge provenance check is cheap, high-value, and bounded. It is not
   a fleet trust layer.
4. **Run one disposable Nix proof.** Build-only flake; no switch, no service
   migration, no cache, no production dependency. Keep it only if it improves
   a present reproducibility or recovery problem.

### Defer indefinitely unless a trigger appears

- **Role mesh and automatic failover:** one online host has no HA problem to
  solve. Future role fields are fine; lease/fencing automation is not.
- **Pull converge, signing ceremony, threshold root, typed IR, and SecretSpec
  runtime resolver:** they are inseparable enough to be safe and too large for
  incidental infrastructure work.
- **Consent, advisor, catalog, WoT, transparency log, and local-fix
  automation:** there is no second user. A prompt around opaque privileged
  code is worse than no prompt.
- **Builder/cache and reproducible APK program:** begin only for external
  privileged-artifact distribution or a real reproducibility incident.
- **Free Sysadmin extraction:** there are zero demonstrated consumers. Keep
  generic code fact-free in-tree.

### Is Nix worth it?

**Not yet as a production migration.** Nix has real substrate-generation and
closure-diff benefits, but this fleet has one live laptop and no Linux host.
Those benefits do not outweigh making the laptop's operational path less
familiar while Android recovery is open.

Keep the build-only flake as an option. Do not switch the Mac until reliability
is quiet, a real exit drill has passed, a recovery window exists, and one
specific substrate defect is improved. If that never happens, mise + Ansible +
the existing release train is the right outcome, not architectural failure.

## 4. Sequencing for motivation and reversibility

The final architecture puts the exit drill after Mac switching, VPS movement,
pull, and consent. That is backwards.

| Step | Deliverable and hard boundary                                                                                                                                            | Coherent stop                                                                              |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------ |
| A    | Finish or explicitly park Fire OS, observability, and restart work. Freeze 2.0 runtime changes during soaks.                                                             | **S0:** known-good current fleet; current just/Ansible/CFEngine is the only control plane. |
| B    | Add worktree ownership/provenance automation, descriptive writer census, and lint; no render/switch.                                                                     | **S1:** safer current operations; no second runtime ownership path.                        |
| C    | Build-only flake and emergency removal instructions; no Mac switch.                                                                                                      | **S2:** evaluated Nix, no Nix dependency; delete the flake to recover the old model.       |
| D    | Acquire VPS only for standalone value. Use existing adapters for a non-primary shadow telemetry/backup role; do not move obs-main.                                       | **S3:** real second host, no mesh; destroying it leaves Mac/fleet unchanged.               |
| E    | Run the Ubuntu exit drill against real Site Model, mise baseline, and Ansible service adapters; induce failure and recover.                                              | **S4:** exit evidence; this gates further Nix investment.                                  |
| F    | After S4, choose one low-coupling Mac substrate change. Keep services under Ansible and prove live rollback.                                                             | **S5:** one reversible substrate improvement.                                              |
| G    | Parameterize only assumptions encountered operating VPS/Mac. No automatic leadership, primary handoff, or pull timer.                                                    | **S6:** explicit multi-host inventory and manual authority.                                |
| H    | Open a separately funded secure-update project only when unattended pull or an external participant is needed. Start with threat model/test harness, not a timer client. | **S7:** honest non-deployment; push-only remains authoritative.                            |

If the operator stops at S1, S3, or S5, the system is simpler or more
resilient than today. A partial signing or consent prototype does not have
that property.

## 5. Kill criteria and leading indicators

| Signal                                                                                                                            | Required action                                                                                                     |
| --------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| Phase 0 cannot produce a reviewed truthful census and lint in two focused weeks.                                                  | Stop adding Site Model abstractions; retain a short inventory note and begin no generator.                          |
| Fire OS, telemetry, or release acceptance is open while migration touches the same device/service.                                | Freeze migration work; finish or explicitly deprioritize the live issue.                                            |
| vps-primary is still unprovisioned 30 days after Phase 3 is discussed.                                                            | Suspend Phases 3, 4, 7, and mesh claims. Do not write Linux twins against imaginary hardware.                       |
| Ownership is unclear or CI needs a broad writer-lint exception.                                                                   | Do not switch that family. Leave it Ansible/Brew-owned.                                                             |
| A Mac substrate change cannot fully roll back and check in one session, or interrupts control-node services.                      | Roll it back, delete that path, and defer production Nix six months. Do not debug forward on the sole control node. |
| Exit drill fails twice, needs Nix internals, or depends on undocumented manual copying.                                           | Treat Nix as net-negative until redesigned; do not advance Mac switching.                                           |
| A provenance gate finds foreign commits, unexplained signing input, or an agent ownership bypass.                                 | Freeze release/trust work and repair ordinary engineering controls first. More signatures are not the remedy.       |
| A pull prototype accepts a one-key manifest, arbitrary playbook/APK hash, absent expiry/sequence state, or ambient secret lookup. | Never enable its timer or call it a pilot; isolate or delete it.                                                    |
| Consent arrives before a device-bound, expiring, single-use grant, enforced capability executor, and privileged APK provenance.   | Do not show the UI. A non-enforcing prompt is deception.                                                            |

At every stop, require demonstrated rollback; tests that fail against the old
or bad behaviour; live evidence for device/service changes; and a short STATUS
or handoff statement of gaps. A green build is never a promotion criterion.

Use a capacity rule too: no 2.0 implementation while more than two live
reliability/release incidents or cross-repo commitments are active. The current
issue queue and in-flight secretspec, LiteLLM, Beads/Ralph, and site work
already consume that capacity. Architecture is the first work to pause; the
functioning fleet is the asset being protected.

## Verdict

Keep one third: finish the fleet, add factual ownership/provenance rails, prove
one reversible substrate path, and provision a VPS only when it has standalone
value. Cut the mesh, trust, consent, cache, public extraction, and autonomous
convergence from the current migration.

That leaves a system the operator can abandon at any point without making it
harder to operate. The present full plan does not.
