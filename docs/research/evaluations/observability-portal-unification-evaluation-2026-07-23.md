# Observability unification vs. portal unification — evaluation

**Date:** 2026-07-23
**Analyst:** Claude Sonnet 5 (interactive session), reviewing an externally-authored proposal
**Trigger:** operator pasted a third-party AI's recommendation to (a) unify metrics/logs/health
into Grafana and (b) replace the landing page with Homer or Glance

---

## The proposal under review

The pasted proposal split "combined web views" into two categories and recommended:

1. **Observability unification** — make Grafana the single pane of glass by adding an
   Elasticsearch-compatible datasource pointed at OpenObserve (for logs), relying on the
   existing VictoriaMetrics/Prometheus datasource (for metrics + blackbox active checks),
   and iframing OliveTin into a Grafana Text panel (for control).
2. **Portal unification** — replace the existing "small landing page" with **Homer**
   (static HTML/YAML, served by Caddy) or **Glance** (single Go binary), on the grounds that
   both fit a no-Docker, Ansible-friendly, native-binary constraint that tools like
   Homepage/Dashy/Heimdall fail (they need Docker/Node/PHP).

Constraints assumed by the proposal: native macOS/Linux, no Docker, Ansible-friendly, low
resource overhead.

## What repo research found — and where the proposal's premises don't hold

| Proposal claim                                                      | What's actually true in this repo                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| ------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Target is "native macOS/Linux"                                      | **macOS-only.** Every `serverapp_*` role (`ansible/roles/serverapp_*/meta/main.yml`) declares `platforms: [macOS]`. There is no Linux server target — the fleet "devices" are unrooted Android handsets (Samsung/Pixel/Fire OS), managed via Termux/ADB/Shizuku, not part of the `serverapp_*` role family at all.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| No Docker constraint needs stating as a hard rule                   | True in spirit, but it's _structural_, not written down as an explicit ban. Every role installs via Homebrew or pinned-sha256 native-binary download (`get_url`+`unarchive`), lifecycle managed entirely by launchd (`bootstrap`/`kickstart`/`bootout`). No Docker/K8s tooling exists anywhere in `ansible/`. The one place this is written down explicitly is `docs/research/prompts/dashboard-framework-research.md`, which says Docker "is not automatically disqualifying, but... must be justified for three devices" — a strong bias, not an absolute ban.                                                                                                                                                                                                                                                                                                                 |
| "Small landing page" is the thing to replace                        | It's a **live, custom Flask + HTMX app** (`control/landing/landing.py`, port 8088), not a static page: it does periodic reachability discovery (`control/landing/discover.py`, hourly LaunchAgent), hide/rescan actions, and is Caddy's catch-all root route. Swapping it for a static Homer/Glance config would be a capability _regression_ (loses live status) unless kept as a supplement, not a replacement.                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| Portal unification is an open, undecided question                   | There's a **second, more capable** app already doing more of this job: the Fleet Dashboard (`control/bin/dashboard.py`, port 4097) — per-device cards, live health probes, human-consent action workflows (e.g. Shizuku authorization retry), long-term JSONL stats. This is the actual "portal" the proposal should have been evaluated against, not the landing page.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| —                                                                   | This exact question — "should stayturgid adopt an existing dashboard/portal framework instead of (or alongside) the custom Flask+HTMX dashboard" — is **already a scoped, deliberately deferred research task**: `docs/research/prompts/dashboard-framework-research.md`, tracked as OPTIONS **T2** ("Deferred") in `docs/options.md`. It explicitly lists Homepage, Backstage, and Homarr as candidates and explicitly says "do not treat Uptime Kuma, Grafana, or a status-page product as a complete answer... do not recommend a large platform merely because it can embed links to the existing custom dashboard" — i.e. it already anticipated and rejected the Homer/Glance-as-portal framing on architectural grounds (no job execution, no approval/consent workflow, no Ansible integration). **No evaluation deliverable has been written yet** — this remains open. |
| Elasticsearch datasource is the way to get OpenObserve into Grafana | The repo's own Grafana datasource fragment (`control/site_contract/sync_templates/fragments/grafana/datasources/stayturgid.yaml.j2`) already anticipates adding OpenObserve as a **Prometheus-compatible** datasource (for metrics), not an Elasticsearch shim (which is a logs/traces integration model). It's commented out / not wired in yet, blocked specifically on **secrets handling** (OpenObserve needs basic auth; no secret is available to the template at provisioning time) — not on missing plugin support. Separately, OpenObserve does have a native Grafana plugin (purpose-built for logs) that would be a better fit than an Elasticsearch shim if logs unification is wanted later.                                                                                                                                                                        |
| Grafana "Fleet Control Room" is close to a unified pane already     | It's explicitly labeled a **D5 scaffold** in its own markdown panel: one datasource (VictoriaMetrics only), per-host stat panels with `noValue: "no metrics pipeline yet"` since no device-metrics producer exists yet, and links (not embeds) out to OpenObserve/OliveTin. It's a foundation, not a finished unification.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| OliveTin via iframe/Text-panel embed                                | Not currently done — OliveTin is reachable via a Grafana dashboard _link_ (external URL) and via Caddy at its own path, not embedded. The `disable_sanitize_html` iframe trick is plausible but untried here; low risk, low value given OliveTin already has its own URL behind Caddy/Tailscale.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |

## Recommendation

**Don't adopt Homer or Glance as a portal replacement.** The proposal's own stated
justification (native binary, Ansible-friendly, no Docker) is real, but it evaluated the
wrong existing artifact (the landing page) instead of the one that actually matters (the
Fleet Dashboard), and reproduces a question the repo already scoped more rigorously and
deliberately deferred. Adopting a link-aggregator now would either (a) sit uselessly next to
the landing page it duplicates, or (b) get conflated with the harder, already-queued
dashboard-framework decision and prejudge it without going through the evaluation the repo's
own research prompt calls for (job execution, approval/consent workflows, Ansible
integration — things Homer/Glance don't do).

**Two separable, real threads instead:**

1. **Finish OpenObserve → Grafana metrics integration** (small, mostly unblocked). This is
   already anticipated in the datasource fragment; the only gap is secret delivery for
   OpenObserve basic auth. This is genuinely "observability unification" work and doesn't
   touch the portal question at all.
2. **Actually run the deferred dashboard-framework evaluation** (`docs/research/prompts/dashboard-framework-research.md`)
   rather than deciding the portal/dashboard question informally from a pasted third-party
   summary. That prompt is self-contained and ready to hand to a research agent; it already
   correctly excludes Homer/Glance-style tools as insufficient (no job execution, no
   approval gates) unless purely additive.

Neither thread requires introducing a new always-running service, and both stay inside the
existing native-binary/launchd/Ansible pattern this repo already uses consistently (see
`ansible/roles/serverapp_blackbox_exporter/` as the cleanest current exemplar of that
pattern).

## Loose ends found during this research (not fixed here)

- **`docs/options.md` OPTIONS T2 is mislabeled/stale relative to its own linked prompt.**
  T2's heading is "Evaluate dashboard/framework options for JS runtime supervision" and its
  body discusses PM2, Uptime Kuma, Pulumi, Jest, `zx`, Shipit, Flightplan — but it links
  `docs/research/prompts/dashboard-framework-research.md` as "the research prompt for this
  work," and that prompt is actually about replacing/augmenting the **Flask fleet dashboard**
  with an Ansible/ops framework (AWX, Semaphore, Django, NiceGUI, Homepage, etc.) — a
  different, larger question than JS runtime supervision. The JS-runtime-supervision
  question already has its own separate, complete deliverable:
  `docs/research/javascript-runtime-supervision-2026-07-13.md`. It looks like T2's link was
  repointed at some point without updating T2's body, leaving the _actual_
  dashboard-framework-research.md deliverable with no OPTIONS entry tracking it. Recommend
  either splitting T2 into two entries or re-titling/re-scoping it next time someone touches
  Track T.
- **OpenObserve ↔ Vector auth is currently broken fleet-wide**, per the most recent handoff
  (`docs/archive/sessions/handoff-2026-07-22-native-agent-k1.md` §"Fix OpenObserve auth
  for Vector"): Vector is running and reading `soft_health.jsonl` but every OpenObserve sink
  write gets `401 Unauthorized` because `OPENOBSERVE_ROOT_PASSWORD` is empty/wrong in the
  Vector LaunchAgent's environment. This blocks _any_ OpenObserve-side unification work
  (Grafana datasource or otherwise) until the operator fixes credentials and Vector is
  restarted and (optionally) `reingest_soft_health.py` is run to backfill dropped events.
  This is the same secrets gap noted in this evaluation's Grafana-datasource comment above —
  it's one fix, not two.
- **No `docs/research/dashboard-framework-evaluation-*.md` deliverable exists.** The prompt
  at `docs/research/prompts/dashboard-framework-research.md` is fully written and ready to
  hand to a research agent, but has never actually been run.
