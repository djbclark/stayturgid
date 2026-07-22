# Vendored dependencies (git submodules).

# ---------- autojs6-typescript (Rhino gotchas/checks for device/autojs6) ----------

# Check whether vendor/autojs6-typescript is at the latest upstream commit.
_vendor_autojs6_typescript_check_impl:
    #!/usr/bin/env bash
    set -euo pipefail
    cd vendor/autojs6-typescript
    git fetch origin --quiet
    pinned_rev="$(git rev-parse HEAD)"
    upstream_rev="$(git rev-parse origin/main)"
    if [ "$pinned_rev" = "$upstream_rev" ]; then
      echo "OK: vendor/autojs6-typescript is at the latest commit ($pinned_rev)"
    else
      echo "STALE: vendor/autojs6-typescript is behind origin/main"
      echo "  pinned:  $pinned_rev"
      echo "  latest:  $upstream_rev"
      echo "  run: just vendor-update-autojs6-typescript"
      exit 1
    fi

vendor-check-autojs6-typescript-legacy:
    @just _vendor_autojs6_typescript_check_impl

# Verify the vendored autojs6-typescript submodule matches upstream's latest commit.
vendor-check-autojs6-typescript:
    @just _vendor_autojs6_typescript_check_impl

# ---------- Update ----------
_vendor_autojs6_typescript_update_impl:
    #!/usr/bin/env bash
    set -euo pipefail
    cd vendor/autojs6-typescript
    git fetch origin --quiet
    before="$(git rev-parse HEAD)"
    git checkout main --quiet
    git pull origin main --quiet
    after="$(git rev-parse HEAD)"
    cd ../..
    if [ "$before" = "$after" ]; then
      echo "vendor/autojs6-typescript already at latest ($after)"
    else
      git add vendor/autojs6-typescript
      echo "vendor/autojs6-typescript updated: $before -> $after"
      echo "Review the toolkit's own changelog/commits between these two revisions,"
      echo "then commit the submodule pointer bump: git commit -m 'chore: bump vendor/autojs6-typescript'"
    fi

vendor-update-autojs6-typescript-legacy:
    @just _vendor_autojs6_typescript_update_impl

# Pull the latest autojs6-typescript commit into vendor/ and stage the pointer bump.
vendor-update-autojs6-typescript:
    @just _vendor_autojs6_typescript_update_impl
