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

Afterwards it commits and pushes whatever site-sync left under
``generated/stayturgid/`` in the site checkout, and only that path: the
checkout is shared with other sessions whose uncommitted work must stay put.
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
AUTOCOMMIT_ENV = "STAYTURGID_SITE_AUTOCOMMIT"
GENERATED_PATHSPEC = f"generated/{PRODUCT}"
# Commit hooks and a push over the network run while the fleet lock is held.
GIT_TIMEOUT_SECONDS = int(os.environ.get("STAYTURGID_SITE_GIT_TIMEOUT_SECONDS", "120"))
# Files git keeps in the git dir while a merge, rebase, cherry-pick or revert is
# unfinished; committing on top of one would fold the deploy into it.
_IN_PROGRESS_MARKERS = ("MERGE_HEAD", "rebase-merge", "rebase-apply", "CHERRY_PICK_HEAD", "REVERT_HEAD")

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


def _git(cwd: Path, env: Mapping[str, str], *args: str) -> tuple[int, str]:
    """Run ``git -C cwd args``; return (exit code, stdout on success or the error text)."""
    # A push that wants credentials must fail now, not wait on a prompt nobody sees.
    child_env = {**env, "GIT_TERMINAL_PROMPT": "0"}
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), *args],
            env=child_env,
            text=True,
            capture_output=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return 124, f"git {args[0]} exceeded {GIT_TIMEOUT_SECONDS}s"
    except OSError as exc:
        return 127, f"cannot run git: {exc}"
    if result.returncode == 0:
        return 0, result.stdout or ""
    return result.returncode, (result.stderr or result.stdout or "").strip()


def autocommit_blocker(site_dir: Path, env: Mapping[str, str]) -> str | None:
    """Return why generated/ changes must not be committed automatically, or None."""
    if env.get(AUTOCOMMIT_ENV, "").strip() == "0":
        return f"{AUTOCOMMIT_ENV}=0"
    rc, git_dir = _git(site_dir, env, "rev-parse", "--absolute-git-dir")
    if rc != 0:
        return f"{site_dir} is not a git checkout"
    if _git(site_dir, env, "symbolic-ref", "-q", "HEAD")[0] != 0:
        return f"{site_dir} has a detached HEAD"
    busy = [marker for marker in _IN_PROGRESS_MARKERS if (Path(git_dir.strip()) / marker).exists()]
    if busy:
        return f"a merge or rebase is in progress in {site_dir} ({busy[0]})"
    return None


def commit_message(repo_root: Path, env: Mapping[str, str]) -> str:
    rc, short = _git(repo_root, env, "rev-parse", "--short", "HEAD")
    suffix = f" {short.strip()}" if rc == 0 and short.strip() else ""
    return f"chore(generated): sync from {PRODUCT}{suffix}"


def _manual_commit(site_dir: Path, message: str) -> str:
    return (
        f"  git -C {site_dir} add -- {GENERATED_PATHSPEC} && "
        f"git -C {site_dir} commit -m '{message}' -- {GENERATED_PATHSPEC} && git -C {site_dir} push"
    )


def _pending_generated(site_dir: Path, env: Mapping[str, str]) -> tuple[int, list[str]]:
    rc, out = _git(site_dir, env, "status", "--porcelain", "--", GENERATED_PATHSPEC)
    if rc != 0:
        return rc, [out]
    return 0, [line for line in out.splitlines() if line.strip()]


def autocommit_generated(site_dir: Path, repo_root: Path, env: Mapping[str, str]) -> None:
    """Commit and push site-sync's output under generated/<product>/ and nothing else.

    Never raises: the files on disk are already what this deploy reads, so a
    failed commit or push is left for the operator rather than stopping phones.
    """
    reason = autocommit_blocker(site_dir, env)
    if reason:
        print(f"site preflight: not committing {GENERATED_PATHSPEC} ({reason})", file=sys.stderr)
        return
    message = commit_message(repo_root, env)
    rc, pending = _pending_generated(site_dir, env)
    if rc != 0:
        print(
            f"WARNING: site preflight: git status failed in {site_dir} ({pending[0]}); "
            f"commit any {GENERATED_PATHSPEC} changes by hand:\n{_manual_commit(site_dir, message)}",
            file=sys.stderr,
        )
        return
    if not pending:
        return
    # The pathspec on commit as well as add matters: a bare `git commit` would
    # also take anything another session had already staged in this checkout.
    for args in (("add", "--", GENERATED_PATHSPEC), ("commit", "-m", message, "--", GENERATED_PATHSPEC)):
        rc, out = _git(site_dir, env, *args)
        if rc != 0:
            print(
                f"WARNING: site preflight: `git {args[0]}` failed in {site_dir} (exit {rc}): {out}\n"
                f"Deploy continues; commit and push by hand:\n{_manual_commit(site_dir, message)}",
                file=sys.stderr,
            )
            return
    print(
        f"site preflight: committed {len(pending)} path(s) under {GENERATED_PATHSPEC} in {site_dir}: {message}",
        file=sys.stderr,
    )
    rc, out = _git(site_dir, env, "push")
    if rc != 0:
        print(
            f"WARNING: site preflight: `git push` failed in {site_dir} (exit {rc}): {out}\n"
            f"Deploy continues; the commit is local only. Push by hand:\n"
            f"  git -C {site_dir} pull --rebase && git -C {site_dir} push",
            file=sys.stderr,
        )
        return
    print(f"site preflight: pushed {site_dir}", file=sys.stderr)


def preview_autocommit(site_dir: Path, env: Mapping[str, str]) -> None:
    """CHECK=1: say what a real deploy would commit; read-only git only."""
    reason = autocommit_blocker(site_dir, env)
    if reason:
        print(
            f"site preflight (dry run): a real deploy would not commit {GENERATED_PATHSPEC} ({reason})",
            file=sys.stderr,
        )
        return
    rc, pending = _pending_generated(site_dir, env)
    if rc != 0:
        print(f"WARNING: site preflight (dry run): git status failed in {site_dir} ({pending[0]})", file=sys.stderr)
        return
    already = "".join(f"\n  {line}" for line in pending)
    print(
        f"site preflight (dry run): a real deploy commits and pushes whatever site-sync changes under "
        f"{GENERATED_PATHSPEC} in {site_dir}" + (f"; already uncommitted there:{already}" if pending else ""),
        file=sys.stderr,
    )


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
    preview_autocommit(site_dir, env)
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
            "commit (no rendered file changed).",
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
        # deploy reads, and a dirty site checkout does not block a deploy.
        listing = "\n".join(f"  {generated / path}" for path in content)
        print(
            f"site preflight: site-sync refreshed {len(content)} generated file(s) this deploy reads:\n{listing}",
            file=sys.stderr,
        )
    autocommit_generated(site_dir, repo_root, env)
