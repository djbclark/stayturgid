# Adding a launchd service

How to add a new user LaunchAgent managed by stayturgid or a site overlay.
Covers the two deployment paths: the **control_node** Ansible role (global
agents under `com.stayturgid.*`) and the **site_agents** Ansible role
(per-site agents under `com.<site_ns>.*`).

## Which path to use

| If the service is...                                  | Use                                    |
| ----------------------------------------------------- | -------------------------------------- |
| Fleet-wide on every Mac control node (every operator) | `control_node` role in stayturgid      |
| Specific to one site/person (e.g. personal tools)     | `site_agents` role in a site-* overlay |

Both paths produce a plist in `~/Library/LaunchAgents/`, bootstrap via
`launchctl bootstrap gui/<uid>`, and are idempotent across repeat applies.

---

## Path A: control_node (stayturgid global)

Add to `ansible/roles/control_node/`. Three files to touch.

### 1. Defaults (`defaults/main.yml`)

Add variables following the existing pattern:

```yaml
stayturgid_my_agent_label: "com.stayturgid.my-agent"
stayturgid_my_agent_plist: >-
  {{ stayturgid_home }}/Library/LaunchAgents/{{ stayturgid_my_agent_label }}.plist
stayturgid_my_agent_enabled: true
```

For agents with a feature flag, add an `_enabled` boolean so operators can turn
it off without deleting code.

### 2. Plist template (`templates/<name>.plist.j2`)

| Pattern          | Keys                                                          | Example                   |
| ---------------- | ------------------------------------------------------------- | ------------------------- |
| KeepAlive server | `RunAtLoad: true`, `KeepAlive: true`, `ThrottleInterval`      | hermes-gateway, dashboard |
| Interval cron    | `RunAtLoad: true`, `StartInterval` or `StartCalendarInterval` | fleet-health, fire-help   |

Always include `StandardOutPath` and `StandardErrorPath` — even `/dev/null` is
better than launchd's default windmill logs.

### 3. Tasks

**agents.yml** — render the plist:

```yaml
- name: Render my-agent LaunchAgent plist
  ansible.builtin.template:
    src: my-agent.plist.j2
    dest: "{{ stayturgid_my_agent_plist }}"
    mode: "0644"
  register: _my_agent_plist
  when: stayturgid_my_agent_enabled | bool
```

**agents_ensure.yml** — add to the service list so launchd state is managed.
Find the appropriate sub-list (e.g. `_core_launchd_agents`) and append:

```yaml
- name: "{{ stayturgid_my_agent_label }}"
  plist: "{{ stayturgid_my_agent_plist }}"
  # health_url: optional HTTP health check (KeepAlive servers only)
```

Respect the existing grouping: core agents first, then feature-flagged agents
with their `when:` condition. The concatenation at the top of the file builds
the full `_mac_launchd_ensure_services` list automatically.

The `launchd_ensure.yml` sub-task handles the rest: probe → reload changed →
load unloaded → restart anomalies → health probe.

### 4. just target (optional)

Add a dedicated just command in `just/services.just`:

```just
my-agent-deploy args="":
    ansible-playbook ansible/playbooks/control_node/site.yml \
      --tags agents -e stayturgid_my_agent_enabled=true {{ args }}

my-agent-status:
    @just landing-page-status "{{ stayturgid_my_agent_label }}" 2>/dev/null || \
      launchctl list | grep {{ stayturgid_my_agent_label }}
```

---

## Path B: site_agents (site overlay)

Add to the site overlay's `roles/site_agents/`. File-by-file guide in that
role's README (e.g. `${OPS_ROOT:-~/ops}/site-djbclark/roles/site_agents/README.md`).
Quick summary:

1. **`defaults/main.yml`** — define `site_agents_<name>_label`, plist path, log paths, config knobs
2. **`templates/<name>.plist.j2`** — Jinja2 template referencing those vars
3. **`tasks/main.yml`** — two blocks:
   - `ansible.builtin.template` to render the plist
   - `ansible.builtin.include_tasks: launchagent.yml` to bootstrap it
4. **`justfile`** — add status check to `site-agents-status` target

The `launchagent.yml` sub-task (shared by all site agents) handles:
probe → bootout-on-change → bootstrap-if-unloaded → kickstart-on-script-change.

---

## Verification

After deploy, confirm the agent is running:

```bash
# control_node path
just deploy-mac

# site path
just site-agents-apply
just site-agents-apply    # second run must show changed=0

# Both paths: check launchd
launchctl list com.stayturgid.my-agent
launchctl print "gui/$(id -u)/com.stayturgid.my-agent"

# Check logs
tail ~/Library/Logs/my-agent.log
```

---

## Common patterns

### KeepAlive server (long-running daemon)

```xml
<key>RunAtLoad</key><true/>
<key>KeepAlive</key><true/>
<key>ThrottleInterval</key><integer>30</integer>
```

Use when the process should run forever and restart on crash. `ThrottleInterval`
prevents rapid crash loops. For servers with an HTTP health endpoint, add
`health_url` to the service entry in `agents_ensure.yml`.

### Interval-based (periodic job)

```xml
<key>StartInterval</key>
<integer>900</integer>
<key>RunAtLoad</key><true/>
```

Use when the process does one unit of work and exits. `RunAtLoad: true` ensures
it fires immediately on load in addition to the interval.

### Calendar-based (scheduled job)

```xml
<key>StartCalendarInterval</key>
<dict>
    <key>Hour</key><integer>4</integer>
    <key>Minute</key><integer>15</integer>
</dict>
<key>RunAtLoad</key><false/>
```

Use for nightly/weekly jobs.

### PATH and environment

launchd's default PATH is `/usr/bin:/bin:/usr/sbin:/sbin`. If the process needs
Homebrew, Python from uv, or user-local bins, add:

```xml
<key>EnvironmentVariables</key>
<dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
</dict>
```

Or use `/usr/bin/env python3` as argv[0] to pick up the user's PATH indirectly.

### Making an agent optional

Set a boolean default in `defaults/main.yml`:

```yaml
stayturgid_my_agent_enabled: false
```

Gate every related task with `when: stayturgid_my_agent_enabled | bool` and
provide a `--tags` or `-e` override in the just target.
