# Remotes 🌐

Reproducible setup for the maintainer's fork-based workflow. `origin` MUST point at the canonical repository, a separate remote (`fork`) MUST be the personal fork that holds feature and fix branches, and `main` MUST pull from canonical while every new branch MUST push to the fork.

## Layout 🗺️

| Remote | URL | Role |
|---|---|---|
| `origin` | `git@github.com:infinito-nexus/core.git` | Canonical / upstream. `main` tracks `origin/main`. Pull target. |
| `fork` | `git@github.com:<user>/infinito-nexus-core.git` | Personal fork. Push target for every branch. |

`main` MUST be tracked against `origin/main` so `git pull` always takes from the canonical repo. `remote.pushDefault` MUST be set to `fork` so every `git push` (and `make git-sign-push` for a branch without upstream, see [sign-push.sh](../../../../scripts/git/sign-push.sh)) lands on the fork, not on the canonical repo.

## One-time Setup ⚙️

You MUST run the setup once after cloning, outside the Claude sandbox, since `.git/config` writes are blocked inside per the Git Safety Protocol in [settings.md](../../tools/agents/claude/settings.md).

```bash
make git-setup-remotes
```

The target wraps [setup-remotes.sh](../../../../scripts/git/setup-remotes.sh) and is idempotent. It detects the current remote layout and applies the rename, re-fetch, upstream wiring, and `remote.pushDefault` config in one step.

If the clone came from the canonical repo (so no fork URL is locally known yet), pass it in once:

```bash
FORK_URL=git@github.com:<user>/infinito-nexus-core.git make git-setup-remotes
```

After this, the expected state is:

```bash
$ git remote -v
fork    git@github.com:<user>/infinito-nexus-core.git (fetch)
fork    git@github.com:<user>/infinito-nexus-core.git (push)
origin  git@github.com:infinito-nexus/core.git (fetch)
origin  git@github.com:infinito-nexus/core.git (push)

$ git config --get remote.pushDefault
fork

$ git rev-parse --abbrev-ref main@{u}
origin/main
```

## Shipping Branches 🚢

Once the remotes are set up, the normal commit flow applies:

1. Create your branch from `main` per [branch.md](branch.md).
2. Commit per [commit.md](commit.md).
3. Push via `make sign-push` (see the `Sign and push` row in [make.md](../../tools/make.md)). The script resolves the target from `remote.pushDefault`, so it pushes the new branch to `fork` by default and leaves the canonical repo untouched.
4. Open the pull request against `origin/main` per [pull-request.md](pull-request.md).
