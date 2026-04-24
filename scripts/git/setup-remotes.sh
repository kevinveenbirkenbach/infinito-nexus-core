#!/usr/bin/env bash
# Set up remotes for the maintainer's fork-based workflow:
#   origin -> canonical (infinito-nexus/core)
#   fork   -> personal fork (kevinveenbirkenbach/infinito-nexus-core or $FORK_URL)
#
# `main` tracks `origin/main` (pulls come from canonical), and
# `remote.pushDefault` is set to `fork` so every new branch and every
# `git push` without args lands on the fork, not on the canonical repo.
#
# Idempotent: re-running after a correct setup is a no-op.
#
# Must run OUTSIDE the Claude sandbox: `.git/config` writes are blocked
# inside per the Git Safety Protocol. See sign-push.sh for the same guard.
set -euo pipefail

CANONICAL_URL="${CANONICAL_URL:-git@github.com:infinito-nexus/core.git}"

if [[ -n "${CLAUDE_CODE:-}${CLAUDECODE:-}" ]]; then
	echo "ERROR: setup-remotes must run outside the Claude sandbox (it writes .git/config)." >&2
	exit 1
fi

has_remote() { git remote get-url "$1" >/dev/null 2>&1; }
remote_url() { git remote get-url "$1" 2>/dev/null || true; }

# --- Resolve the fork URL -----------------------------------------------
# Preference order:
#   1. $FORK_URL env var (explicit override).
#   2. Existing `fork` remote (already set up).
#   3. Existing `origin` remote IFF it does not point at the canonical URL
#      (clone-from-fork case, rename needed).
resolve_fork_url() {
	if [[ -n "${FORK_URL:-}" ]]; then
		echo "${FORK_URL}"
		return
	fi
	local url
	url="$(remote_url fork)"
	if [[ -n "${url}" ]]; then
		echo "${url}"
		return
	fi
	url="$(remote_url origin)"
	if [[ -n "${url}" && "${url}" != "${CANONICAL_URL}" ]]; then
		echo "${url}"
		return
	fi
	echo ""
}

FORK_RESOLVED="$(resolve_fork_url)"

if [[ -z "${FORK_RESOLVED}" ]]; then
	echo "ERROR: cannot determine the fork URL." >&2
	echo "  Set FORK_URL=git@github.com:<user>/infinito-nexus-core.git and re-run." >&2
	exit 1
fi

# --- Configure `origin` = canonical -------------------------------------
if has_remote origin; then
	current_origin="$(remote_url origin)"
	if [[ "${current_origin}" != "${CANONICAL_URL}" ]]; then
		# `origin` currently points at the fork. Move it aside, then re-add
		# pointing at canonical. Use rename when possible so per-branch
		# tracking refs (remotes/origin/*) migrate automatically.
		if has_remote fork; then
			# Both `origin` (=fork) and `fork` exist. Drop the stale
			# `origin` remote and add canonical fresh.
			git remote remove origin
			git remote add origin "${CANONICAL_URL}"
		else
			git remote rename origin fork
			git remote add origin "${CANONICAL_URL}"
		fi
	fi
else
	git remote add origin "${CANONICAL_URL}"
fi

# --- Configure `fork` ---------------------------------------------------
# If an old `upstream` remote is still around and points at canonical,
# drop it (its role is now played by `origin`).
if has_remote upstream; then
	if [[ "$(remote_url upstream)" == "${CANONICAL_URL}" ]]; then
		git remote remove upstream
	fi
fi

if has_remote fork; then
	if [[ "$(remote_url fork)" != "${FORK_RESOLVED}" ]]; then
		git remote set-url fork "${FORK_RESOLVED}"
	fi
else
	git remote add fork "${FORK_RESOLVED}"
fi

# --- Fetch under the new names ------------------------------------------
git fetch --quiet origin
git fetch --quiet fork || true

# --- `main` tracks `origin/main` (pulls from canonical) -----------------
if git rev-parse --verify --quiet main >/dev/null; then
	if git rev-parse --verify --quiet origin/main >/dev/null; then
		git branch --set-upstream-to=origin/main main >/dev/null
	fi
fi

# --- Default push target = fork -----------------------------------------
git config remote.pushDefault fork
git config push.default current

# --- Report final state -------------------------------------------------
echo "Remotes:"
git remote -v
echo
echo "remote.pushDefault = $(git config --get remote.pushDefault)"
echo "push.default       = $(git config --get push.default)"
if main_upstream="$(git rev-parse --abbrev-ref main@{u} 2>/dev/null)"; then
	echo "main tracks        = ${main_upstream}"
fi
