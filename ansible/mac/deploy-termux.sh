#!/usr/bin/env bash
# Run the Termux userland Ansible playbook for one device.
# Usage: ./deploy-termux.sh <s24|p7a|host>
set -euo pipefail
trap 'echo "interrupted" >&2; exit 130' INT TERM

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HOST="${1:?usage: deploy-termux.sh <s24|p7a>}"

case "$HOST" in
  s24) SSH_TARGET="s24" ;;
  p7a) SSH_TARGET="p7a" ;;
  *)   SSH_TARGET="$HOST" ;;
esac

echo "Checking SSH to $SSH_TARGET..."
if ! ssh -o BatchMode=yes -o ConnectTimeout=8 -o LogLevel=ERROR "$SSH_TARGET" 'echo termux_ssh_ok'; then
  echo "ERROR: cannot SSH to $SSH_TARGET — fix keys/Tailscale first" >&2
  exit 1
fi

if ! command -v ansible-playbook >/dev/null 2>&1; then
  echo "ERROR: ansible-playbook not found (brew install ansible)" >&2
  exit 1
fi

ansible-galaxy collection install -r "$ROOT/ansible/requirements.yml" -p "$ROOT/.ansible/collections" >/dev/null

cd "$ROOT"
ANSIBLE_CONFIG="$ROOT/ansible/ansible.cfg" \
  ansible-playbook ansible/playbooks/termux-userland.yml --limit "$HOST"

echo "Done. Verify: ssh $SSH_TARGET '~/stayturgid-repair.sh'"
