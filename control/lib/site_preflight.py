"""Bring the site overlay's generated copy and Vector current before a fleet deploy.

``just deploy`` reads inventory and fragments from the site's
``generated/stayturgid/`` copy, which only ``site-sync`` refreshes, and Vector
only loads its fragments when the ``vector`` serverapp is activated. Neither
used to run as part of a deploy, so on 2026-10-03 the copy was found three days
stale: a product inventory change had no effect on a deploy, and new Vector
fragments had never gone live.

Both steps shell out to the product's own ``just site-sync`` /
``just site-serverapps`` recipes so this module inherits their interpreter
selection, refusals and exit codes instead of re-implementing them.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Mapping

PRODUCT = "stayturgid"
LOCKFILE_NAME = ".lockfile.yml"
SKIP_ENV = "STAYTURGID_SKIP_SITE_PREFLIGHT"
# site-serverapps runs an Ansible play that waits up to ~30 s for Vector's
# health endpoint; site-sync is a few seconds. A hang must not hold the fleet
# lock indefinitely.
PREFLIGHT_TIMEOUT_SECONDS = int(os.environ.get("STAYTURGID_SITE_PREFLIGHT_TIMEOUT_SECONDS", "600"))
# Deploy stopped because site-sync rewrote generated content that should be
# reviewed and committed before it reaches devices. Distinct from 1/2/3/124.
EXIT_GENERATED_CHANGED = 4

# format_plan() in control/site_contract/serverapps.py prints "  create  <plist>"
# only when the site-namespace launchd plist does not exist yet, i.e. Vector was
# never activated for this site.
_FIRST_ACTIVATION = re.compile(r"^\s+create\s+\S+\.plist\b", re.MULTILINE)


class SitePreflightError(RuntimeError):
    """A pre-deploy site step failed or needs operator action; the deploy must stop."""

    def __init__(self, message: str, *, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def should_skip(site_dir: Path, repo_root: Path, environ: Mapping[str, str]) -> str | None:
    """Return why the preflight does not apply here, or None when it should run."""
    if environ.get(SKIP_ENV, "").strip() == "1":
        return f"{SKIP_ENV}=1"
    site = site_dir.resolve()
    product = repo_root.resolve()
    # A config inside the product checkout (e.g. ansible/ansible.cfg) is not a
    # site overlay; site-sync refuses to write into the product tree.
    if site == product or product in site.parents:
        return f"{site} is inside the product checkout, not a site overlay"
    return None


def generated_digest(site_dir: Path) -> dict[str, str]:
    """Map each file under generated/<product>/ to its sha256."""
    root = site_dir / "generated" / PRODUCT
    if not root.is_dir():
        return {}
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def changed_paths(before: Mapping[str, str], after: Mapping[str, str]) -> list[str]:
    return sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))


def content_changes(changed: list[str]) -> list[str]:
    """Drop the lockfile: site-sync restamps it on every product commit even
    when no rendered file changed, so it alone says nothing about the deploy."""
    return [path for path in changed if path != LOCKFILE_NAME]


def is_first_vector_activation(plan_text: str) -> bool:
    return bool(_FIRST_ACTIVATION.search(plan_text))


def _run_recipe(
    recipe: str,
    site_dir: Path,
    repo_root: Path,
    env: Mapping[str, str],
    *args: str,
    capture: bool = False,
) -> tuple[int, str]:
    just = shutil.which("just", path=env.get("PATH"))
    if just is None:
        raise SitePreflightError("just not found on PATH (brew install just) — cannot run site-sync/site-serverapps")
    cmd = [just, "--justfile", str(repo_root / "justfile"), recipe, f"dir={site_dir}", *args]
    child_env = {**env, "STAYTURGID_SITE_DIR": str(site_dir)}
    try:
        result = subprocess.run(
            cmd,
            cwd=repo_root,
            env=child_env,
            text=True,
            capture_output=capture,
            timeout=PREFLIGHT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return 124, f"{recipe} exceeded {PREFLIGHT_TIMEOUT_SECONDS}s"
    output = ((result.stdout or "") + (result.stderr or "")) if capture else ""
    return result.returncode, output


def preview(site_dir: Path, repo_root: Path, env: Mapping[str, str], *, activate_vector: bool) -> int:
    """CHECK=1: report what site-sync and the vector serverapp would change; write nothing."""
    reason = should_skip(site_dir, repo_root, env)
    if reason:
        print(f"site preflight: skipped ({reason})", file=sys.stderr)
        return 0
    print("site preflight (dry run): site-sync", file=sys.stderr)
    worst, _ = _run_recipe("site-sync", site_dir, repo_root, env, "mode=dry-run")
    if worst != 0:
        print(f"WARNING: site-sync dry run exited {worst} — a real deploy would stop here.", file=sys.stderr)
    if activate_vector:
        print("site preflight (dry run): site-serverapps apps=vector", file=sys.stderr)
        rc, _ = _run_recipe("site-serverapps", site_dir, repo_root, env, "mode=dry-run", "apps=vector")
        if rc != 0:
            print(f"WARNING: vector serverapp dry run exited {rc} — a real deploy would stop here.", file=sys.stderr)
            worst = worst or rc
    return worst


def apply(site_dir: Path, repo_root: Path, env: Mapping[str, str], *, activate_vector: bool) -> None:
    """Re-render generated/<product>/ and activate Vector; raise SitePreflightError to stop the deploy."""
    reason = should_skip(site_dir, repo_root, env)
    if reason:
        print(f"site preflight: skipped ({reason})", file=sys.stderr)
        return
    generated = site_dir / "generated" / PRODUCT

    print("site preflight: site-sync", file=sys.stderr)
    before = generated_digest(site_dir)
    rc, _ = _run_recipe("site-sync", site_dir, repo_root, env)
    if rc != 0:
        raise SitePreflightError(
            f"site-sync failed (exit {rc}); deploy stopped before Ansible because {generated} "
            "may not match the product checkout. Fix the error above (for hand-edited generated "
            f"files: review, then `just site-sync force-generated=1` from {site_dir}) and re-run. "
            f"Set {SKIP_ENV}=1 to bypass intentionally.",
            exit_code=rc,
        )
    changed = changed_paths(before, generated_digest(site_dir))
    content = content_changes(changed)
    if changed and not content:
        print(
            f"site preflight: site-sync restamped {generated / LOCKFILE_NAME} to the current product "
            "commit (no rendered file changed); commit it with your next site change.",
            file=sys.stderr,
        )

    if activate_vector:
        # Vector reads its fragment files straight from generated/ at start, so
        # freshly synced fragments are already what the next restart will load;
        # activating now validates them and reloads only if something changed.
        print("site preflight: site-serverapps apps=vector", file=sys.stderr)
        rc, plan_text = _run_recipe(
            "site-serverapps", site_dir, repo_root, env, "mode=dry-run", "apps=vector", capture=True
        )
        print(plan_text, end="", file=sys.stderr)
        if rc != 0:
            raise SitePreflightError(
                f"vector serverapp plan failed (exit {rc}); deploy stopped before Ansible. "
                f"Inspect with `just site-serverapps mode=dry-run apps=vector` from {site_dir}.",
                exit_code=rc,
            )
        if is_first_vector_activation(plan_text):
            # Own mode installs Vector and a new launchd job; that is an opt-in
            # for the site operator, not a side effect of deploying phones.
            print(
                "site preflight: Vector has never been activated for this site — not activating it "
                f"during a deploy. Opt in once with `just site-serverapps apps=vector` from {site_dir}.",
                file=sys.stderr,
            )
        else:
            rc, _ = _run_recipe("site-serverapps", site_dir, repo_root, env, "apps=vector")
            if rc != 0:
                raise SitePreflightError(
                    f"vector serverapp activation failed (exit {rc}); deploy stopped before Ansible. "
                    "The role runs `vector validate` before any reload, so on a validation failure "
                    "the running Vector keeps its old topology — but it reads the fragments in "
                    f"{generated / 'fragments' / 'vector'} directly at start, so its next restart "
                    "will load them. Fix or revert them now, then check `curl -s "
                    "http://127.0.0.1:8686/health` and the Vector log. "
                    f"Set {SKIP_ENV}=1 to bypass intentionally.",
                    exit_code=rc,
                )

    if content:
        # Not a stop: the refreshed files are already on disk and are what this
        # deploy reads, and a dirty site checkout does not block a deploy. Say
        # what changed so it gets committed, and carry on.
        listing = "\n".join(f"  {generated / path}" for path in content)
        print(
            f"site preflight: site-sync refreshed {len(content)} generated file(s) this deploy reads:\n{listing}\n"
            f"Commit them in {site_dir} afterwards:\n"
            f"  git -C {site_dir} add generated/{PRODUCT} && git -C {site_dir} commit -m "
            f"'chore(generated): sync from {PRODUCT}'",
            file=sys.stderr,
        )
