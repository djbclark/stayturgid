# Prompt: evaluate dashboard frameworks for stayturgid

Copy everything below the horizontal rule into a capable research/coding AI. The
prompt is deliberately self-contained: reading the linked repository material will
improve the answer, but a useful investigation must still be possible without it.

---

Investigate whether the stayturgid project should replace, substantially reduce, or
retain its custom fleet dashboard by adopting an existing Ansible dashboard,
automation console, operations framework, or extensible web-dashboard framework.

This is a research and recommendation task. Do not implement, install, deploy, or
configure a replacement dashboard unless separately authorized.

## Project context

stayturgid manages a small private fleet of unrooted Android devices from an Apple
Silicon Mac control node. The current fleet is:

- `s24`: Samsung Galaxy S24 on a recent Android release; preferred live-test device.
- `p7a`: Google Pixel 7a and often a daily driver.
- `hd8`: older Amazon Fire HD 8 / Fire OS device with materially different behavior
  and USB-oriented recovery.

The system keeps wireless ADB, Termux SSH, Shizuku, AutoJs6 automation, CFEngine,
and an optional FIRERPA recovery channel working across reboots. Ansible is the main
configuration/deployment mechanism. Most host-side orchestration and monitoring is
Python. Python is the project's default implementation language unless another
language has a compelling technical advantage. GNU Make is currently the operator
command interface, with a staged migration to `just` planned later.

The repository is public:

- GitHub: <https://github.com/djbclark/stayturgid>
- Local checkout, when available: `~/stayturgid`

## Current dashboard

The dashboard is a custom Flask + HTMX application on the Mac control node. It binds
to `127.0.0.1:4097`, is normally exposed through Caddy, and is reachable only through
the private Tailscale environment. Its primary code is:

- Local: `~/stayturgid/control/bin/dashboard.py`
  GitHub: <https://github.com/djbclark/stayturgid/blob/master/control/bin/dashboard.py>
- Local: `~/stayturgid/control/templates/dashboard.html`
  GitHub: <https://github.com/djbclark/stayturgid/blob/master/control/templates/dashboard.html>
- Local: `~/stayturgid/control/templates/_device_card.html`
  GitHub: <https://github.com/djbclark/stayturgid/blob/master/control/templates/_device_card.html>
- Templates directory:
  <https://github.com/djbclark/stayturgid/tree/master/control/templates>
- Static assets:
  <https://github.com/djbclark/stayturgid/tree/master/control/static>

The current dashboard provides:

- A card for each Android device.
- Static inventory data such as alias, label, USB serial, LAN IP, and Tailscale IP.
- Latest fleet-health data and freshness.
- Per-service state for SSH, the Termux boot loop, localhost ADB port 5555,
  Shizuku, accessibility services, AutoJs6, CFEngine, and related repair loops.
- FIRERPA version and service state.
- Current issue tags, consecutive failure counts, and active/recovered distinctions.
- Immediate live health probes through an HTMX action.
- Recent errors collected from device logs.
- Long-term JSONL statistics and selectable time ranges.
- Links to SSH, CFEngine, and FIRERPA endpoints.
- Human-action-needed descriptions for Android operations that cannot be safely or
  legally automated.

One representative human-action workflow is Shizuku authorization. When a device
reports `shizuku_down`, the dashboard offers **open Shizuku and test rish**. The
server opens the Shizuku launcher through an existing device shell and then runs this
canonical probe over Termux SSH:

```console
~/.stayturgid/bin/rish -c 'id -u'
```

Only UID `2000` counts as success. Android may still require the operator to tap
**Allow all the time**. The dashboard must never imply that it can bypass or automate
Android consent. It must let the operator retry immediately after granting consent
instead of waiting for the next scheduled supervisor cycle.

Other likely future dashboard actions include:

- Run a read-only device health probe.
- Retry an operation that was blocked on human consent.
- Run a narrowly scoped Ansible playbook against one selected device.
- Run Ansible check mode before a change.
- Request an unlocked/on screen and wait for the operator.
- Guide an accessibility toggle that Android requires the user to perform.
- Present progress, timeouts, failures, and recovery guidance.
- Require explicit approval before disruptive actions.
- Record who requested an action and what happened.

The current data is primarily local files rather than a database:

- `~/.config/stayturgid/devices.conf`
- `~/.config/stayturgid/logs/fleet-health.log`
- `~/.config/stayturgid/logs/firerpa-health.log`
- `~/.config/stayturgid/logs/access-monitor.log`
- `~/.config/stayturgid/logs/errors.log`
- state files below `~/.config/stayturgid/state/`
- JSONL statistics accumulated by the control-node monitoring processes

The device-specific health, repair, transport, and consent logic should remain in
stayturgid's Python and Ansible modules. The desired framework would absorb generic
web application, job execution, scheduling, authentication, authorization, progress,
history, audit, and presentation work. A framework that merely requires all the same
custom logic to be rewritten as framework plugins offers little value.

## Architectural constraints

The preferred solution should:

- Work well for a small personal fleet rather than require enterprise-scale
  infrastructure.
- Run on Apple Silicon macOS or have a clearly supportable deployment model there.
- Bind only to localhost and work behind Caddy and Tailscale.
- Avoid a public SaaS dependency and keep fleet/device data local.
- Prefer Python extension points.
- Integrate cleanly with existing Ansible inventory, roles, playbooks, limit patterns,
  check mode, and tags.
- Support asynchronous jobs, streamed progress, cancellation, bounded timeouts, and
  durable history.
- Distinguish read-only actions from mutating or disruptive actions.
- Support explicit approval gates and human-consent states.
- Provide authentication, authorization, CSRF protection, secure secret handling,
  and an audit trail appropriate to a privileged operations interface.
- Permit device-centric status cards and action panels, not only a list of Ansible
  job templates.
- Permit gradual adoption alongside the current Flask + HTMX dashboard.
- Preserve direct access to raw logs and diagnostic details.
- Avoid weakening recovery access or making basic fleet health dependent on a large
  fragile control-plane stack.

Docker, Kubernetes, PostgreSQL, Redis, and message queues are not automatically
disqualifying, but their operational cost must be justified for three devices. State
clearly when a candidate requires or strongly prefers them.

## Source material

Reading these files is strongly recommended, but do not make the usefulness of your
answer depend on access to the local checkout.

Project rules and current state:

- `~/stayturgid/AGENTS.md`
  <https://github.com/djbclark/stayturgid/blob/master/AGENTS.md>
- `~/stayturgid/README.md`
  <https://github.com/djbclark/stayturgid/blob/master/README.md>
- `~/stayturgid/docs/README.md`
  <https://github.com/djbclark/stayturgid/blob/master/docs/README.md>
- `~/stayturgid/docs/coding-rules.md`
  <https://github.com/djbclark/stayturgid/blob/master/docs/coding-rules.md>
- `~/stayturgid/.cursor/rules/`
  <https://github.com/djbclark/stayturgid/tree/master/.cursor/rules>
- `~/stayturgid/docs/handoff.md`
  <https://github.com/djbclark/stayturgid/blob/master/docs/handoff.md>
- `~/stayturgid/docs/options.md`
  <https://github.com/djbclark/stayturgid/blob/master/docs/options.md>
- `~/stayturgid/docs/architecture/components/control.md`
  <https://github.com/djbclark/stayturgid/blob/master/docs/architecture/components/control.md>

Relevant implementation:

- `~/stayturgid/control/bin/fleet_health_monitor.py`
  <https://github.com/djbclark/stayturgid/blob/master/control/bin/fleet_health_monitor.py>
- `~/stayturgid/control/bin/check_fleet_health.py`
  <https://github.com/djbclark/stayturgid/blob/master/control/bin/check_fleet_health.py>
- `~/stayturgid/control/lib/fleet_health.py`
  <https://github.com/djbclark/stayturgid/blob/master/control/lib/fleet_health.py>
- `~/stayturgid/control/lib/stats.py`
  <https://github.com/djbclark/stayturgid/blob/master/control/lib/stats.py>
- `~/stayturgid/ansible/roles/control_node/`
  <https://github.com/djbclark/stayturgid/tree/master/ansible/roles/control_node>
- `~/stayturgid/ansible/playbooks/`
  <https://github.com/djbclark/stayturgid/tree/master/ansible/playbooks>
- `~/stayturgid/ansible/inventory/`
  <https://github.com/djbclark/stayturgid/tree/master/ansible/inventory>

Related research and plans:

- JavaScript/runtime-supervision research:
  <https://github.com/djbclark/stayturgid/blob/master/docs/research/javascript-runtime-supervision-2026-07-13.md>
- Planned Make-to-`just` migration:
  <https://github.com/djbclark/stayturgid/blob/master/docs/operations/plans/just-migration-plan.md>
- Ordered outstanding-fix plan:
  <https://github.com/djbclark/stayturgid/blob/master/docs/operations/plans/outstanding-fix-priorities-2026-07-13.md>

## Candidates to investigate

Search for additional strong candidates, but prioritize self-hostable systems that
can actually execute jobs, record history, and support approvals. At minimum,
evaluate the relevant parts of these projects. Use current official documentation
and repositories rather than relying on memory.

Ansible-oriented tools:

- Ansible Runner: <https://github.com/ansible/ansible-runner>
- AWX: <https://github.com/ansible/awx>
- Semaphore UI: <https://github.com/semaphoreui/semaphore>
- Event-Driven Ansible / Rulebook: <https://github.com/ansible/ansible-rulebook>
- ARA Records Ansible: <https://github.com/ansible-community/ara>
- Ansible Navigator, if relevant: <https://github.com/ansible/ansible-navigator>

Operations and extensible administration frameworks:

- Django: <https://github.com/django/django>
- Flask-AppBuilder: <https://github.com/dpgaspar/Flask-AppBuilder>
- Flask-Admin: <https://github.com/pallets-eco/flask-admin>
- NetBox and its plugin/job framework: <https://github.com/netbox-community/netbox>
- Rundeck: <https://github.com/rundeck/rundeck>
- Cockpit: <https://github.com/cockpit-project/cockpit>

Python dashboard/application frameworks:

- NiceGUI: <https://github.com/zauberzeug/nicegui>
- Dash: <https://github.com/plotly/dash>
- Panel: <https://github.com/holoviz/panel>
- Streamlit, only if it can support safe operations workflows:
  <https://github.com/streamlit/streamlit>

Portal and developer-platform candidates, only where they offer meaningful action
or plugin capabilities beyond links and generic uptime widgets:

- Homepage: <https://github.com/gethomepage/homepage>
- Backstage: <https://github.com/backstage/backstage>
- Homarr: <https://github.com/homarr-labs/homarr>

Do not treat Uptime Kuma, Grafana, or a status-page product as a complete answer.
They may be useful components, but generic uptime graphs do not solve Ansible job
execution, Android consent workflows, or safe device actions. Similarly, do not
recommend a large platform merely because it can embed links to the existing custom
dashboard.

## Evaluation questions

For every serious candidate, investigate and report:

1. Current project health: release cadence, maintenance activity, community, license,
   security posture, and likelihood of remaining maintained.
2. Apple Silicon/macOS support and any Linux-only assumptions.
3. Required infrastructure: containers, Kubernetes, PostgreSQL, Redis, workers,
   message queues, systemd, or cloud services.
4. Whether it can bind to localhost and operate correctly behind Caddy/Tailscale.
5. Authentication, RBAC, CSRF protection, secret storage, audit logs, and approval
   workflows.
6. Ansible integration:
   - inventory and variable support;
   - playbook, role, and ad hoc job launching;
   - host limiting and tags;
   - check mode;
   - event/progress streaming;
   - cancellation and timeouts;
   - job history and artifacts;
   - credentials and vault integration;
   - approval gates.
7. Ability to incorporate existing Python health probes, local log/state files, and
   JSONL statistics.
8. Ability to render device-centric cards and current health, rather than only
   playbook-centric job history.
9. Ability to implement immediate actions such as probe, retry, open-on-device, and
   verify-after-human-consent.
10. Async execution behavior: worker isolation, concurrency limits, duplicate-job
    prevention, progress, cancellation, and cleanup after crashes.
11. Extension/plugin API quality, preferred implementation language, testing story,
    and likely amount of custom code.
12. Upgrade, backup, migration, and routine operational burden for a three-device
    private fleet.
13. Whether adoption would eliminate meaningful custom code or simply move it into
    plugins and configuration.
14. Compatibility with a staged migration that keeps the existing Flask + HTMX UI
    available until replacement features are proven.
15. Failure modes: what fleet functions remain available when the dashboard or its
    database/job workers are down?

Give approximate evidence-backed estimates of:

- custom code removed;
- new integration/plugin code required;
- persistent services and databases added;
- ongoing maintenance burden;
- migration complexity and risk.

## Architectural distinctions

Keep these concerns separate in the analysis:

1. Current fleet status and historical visualization.
2. Ansible job execution and progress reporting.
3. Custom Android actions, recovery mechanisms, and human-consent workflows.
4. Generic service links and landing-page functions.
5. Scheduling/monitoring that already runs independently of the web UI.

A combination may be better than one product. For example, the existing small
device-facing Flask/HTMX UI could remain while Ansible Runner, Semaphore, Rundeck, or
another engine provides job execution and history. Explicitly compare compositional
architectures against complete replacement.

## Required deliverable

If you have access to the repository, create a dated research document under:

```text
~/stayturgid/docs/research/dashboard-framework-evaluation-YYYY-MM-DD.md
```

If you do not have repository access, produce the same document as your response in
Markdown.

The document must include:

1. Executive summary and one clear recommendation.
2. A comparison table covering all credible candidates.
3. Detailed analysis of the strongest candidates.
4. A short rejection rationale for candidates that do not fit.
5. A proposed target architecture showing which component owns:
   - health/status reads;
   - historical data;
   - Ansible execution;
   - custom Android actions;
   - authentication/authorization;
   - approval and audit history.
6. Security analysis, including CSRF, command injection, secrets, RBAC, and the
   danger of exposing privileged device actions through a web interface.
7. Operational-burden analysis for Apple Silicon macOS and a three-device fleet.
8. Estimated custom-code reduction and new integration code.
9. A staged migration or proof-of-concept plan with explicit rollback points.
10. Clear criteria for abandoning the migration and retaining Flask + HTMX.
11. Links to the primary sources used, with access dates or version numbers where
    useful.

State one of these conclusions explicitly:

- Retain the current dashboard.
- Retain it but add a framework-backed job runner.
- Migrate selected features while retaining the device UI.
- Replace it substantially.
- Replace it completely.

If a proof of concept is warranted, define the smallest useful experiment. A good
default is one read-only S24 health probe plus one approval-aware Ansible action.
Specify success/failure criteria, but do not perform the experiment without separate
authorization.

If working in the repository, add a concise link and decision entry to
`docs/options.md` and update `docs/README.md` if appropriate. Preserve unrelated
worktree changes. Do not modify production dashboard code, devices, Caddy, launchd,
or persistent host software. Run existing documentation/code checks relevant to the
files changed. Commit and push only the research/documentation changes if the
repository's rules authorize that normal completion workflow.
