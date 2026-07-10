#!/usr/bin/env bash
# Install UI-TARS-1.5-7B GGUF + mmproj via Ansible (control_node/vlm.yml).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
export ANSIBLE_CONFIG="${REPO_ROOT}/ansible/ansible.cfg"

exec ansible-playbook "${REPO_ROOT}/ansible/playbooks/control_node/site.yml" \
  --tags vlm-models \
  -e stayturgid_vlm_enabled=true
