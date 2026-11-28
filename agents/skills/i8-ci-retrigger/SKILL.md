---
name: i8-ci-retrigger
description: >
  Retrigger the jobs one or more finished CI runs did not pass as the priority line, the regular line following: print and check the line, then hand push and trigger to the operator. Infinito.Nexus specific.
routines: []
---

Follow the instructions from AGENTS.md, then retrigger exactly as this skill describes. Begin by clarifying every open requirement with the `kvb-think-listen` skill, then work under the `kvb-org-robot` skill. Never push and never dispatch yourself: both are the operator's, handed over as rows.

# Retrigger a run

A retrigger puts the failed selections of the named run(s) on the priority
line, each as the exact token it failed in, and then the run continues with
the regular line as usual, resuming behind the green stretch the first run
proved. Building a line from scratch for open questions is the
`i8-ci-trigger-priority` skill instead.

Never skip or shrink the regular line: no `offset` past its end, no raw
`gh workflow run ... -f offset=...`, no `--apps` to narrow the retrigger to
the failed roles. The trigger computes the offset; take it as it comes.

## 1. Runs

The runs are the ones the operator names (URL or id); none named: the latest
deploy run on the current branch. Several runs, for example a fork run and an
upstream PR run of the same branch, are one `--run` each: the priority line is
the union of their failed tokens, deduplicated and sorted, while the
configuration (distros, mode, chunk gate, workspace, ...) and the offset come
from the **first** `--run`, so name the run whose configuration should carry
first. A row ahead of the first run's window that another run only cancelled
is not retriggered under `--strict`: by design, only hard failures return. A bare id resolves against the current branch's repository, so a run
on another repository needs its URL. The dispatch always goes to the current
branch's own repository (`gh.resolve_repo`), whichever repositories the runs
came from.

## 2. Ask

One `AskUserQuestion` call with two questions, the first option of each the
recommended one:

| Question | Option | Flag |
|---|---|---|
| Which jobs? | hard failures (❌) only, exact axes | `--strict` |
| | also cancelled, aborted and still-running jobs, exact axes | none |
| | NOT axis-exact: hard failures as role names, the rest exact | `--roles-only` |
| | NOT axis-exact: every job not green as role names, axes to the rotation | `--any-axes` |
| What then? | push + trigger | |
| | only trigger | |
| | only print | |

"Retrigger the failed jobs" means `--strict`: without it every cancelled or
still-running job joins the line (measured: 195 tokens against 63 real
failures). `--roles-only` and `--any-axes` give up the exact combinations;
offer them only as labelled above and pick them only on the operator's
explicit word, never as a default.

## 3. Print and check

Run in the worktree of the run's branch, with the flag picked in step 2:

```bash
python -m cli.administration.deploy.ci.trigger --failed <flag> --run <url 1> --run <url 2> --print > /tmp/<slug>-line.txt 2> /tmp/<slug>-summary.txt
```

stdout is the line, one space between tokens, exactly as the dispatch sends
it. It can run to ~10 KB: never paste it into the chat or into a row; cite the
file and its token count. stderr is the summary: failed and never-deployed
counts per run, the token count of the union, the priority rows the planner
would plan for that line, where the regular line resumes, the carried
configuration and the dispatch target.

The line is validated offline (`validate.problems`, the check
`call-orchestrator.yml` runs first) and planned before anything is printed.
stdout holds the line only on exit 0; on any other status it is empty and
stderr says why:

| Exit | Meaning | Then |
|---|---|---|
| 0 | line on stdout, summary on stderr | check the counts below |
| 1 | a token cannot deploy on the branch | report the token stderr names; never drop it to get the dispatch through |
| 2 | argument error | fix the command |
| 3 | nothing failed in the run(s) | report that and stop |
| 4 | the planner aborted on the line (an offset that names no row, more chunk blocks than `call-orchestrator.yml` declares) | report the planner's message and stop |
| 5 | no deploy run found on the branch | name the run explicitly |
| 6 | a source run could not be read: a `gh` call failed (auth, network, unknown run) or the URL is malformed; stderr names the run | fix the URL or report the `gh` error |

Then read `Priority rows planned: <P> of <D> discovered`. `D` is how many rows
the priority line expands to, `P` how many of them the planner puts into a
chunk:

- `D` different from the token count: some entries are bare role names (a
  never-deployed priority entry, `--roles-only`, `--any-axes`) and expand to
  several rows, or a token covers more than one row; say which before
  handing over.
- `P` lower than `D` happens only under a run job limit
  (`INFINITO_CI_JOB_LIMIT` above 0): the budget does not reach every
  priority row. Stop and report it. With the default limit of 0 every
  priority row is planned, so `P` equals `D` and proves nothing more.

The filesystem is the one axis the tokens leave to the rotation (the
`cli.administration.deploy.ci.selections` module says why), so a replayed
token is axis-exact in everything but the filesystem.

## 4. Hand over

Pushing is the operator's (AGENTS.md, Pushing) and `gh workflow run` is an
`ask` rule, so every step goes to the operator as rows of the
`kvb-org-operator` skill:

```bash
operator.py add <slug>-cancel --dir <abs worktree> --command "gh run cancel <id> --repo <repo>" --reason "the wrong run <id> is still deploying on this branch" --check manual
operator.py add <slug>-push --dir <abs worktree> --command "<push command from AGENTS.md>" --reason "agents never push" --check pushed:<abs worktree>
operator.py add <slug>-trigger --dir <abs worktree> --command "python -m cli.administration.deploy.ci.trigger --failed <flag> --run <url 1> --run <url 2>" --reason "dispatch is an ask rule; <N> tokens, <P> priority rows planned, regular line resumes at <offset>" --check manual
```

- **cancel**: only while an earlier wrong run is still going, and first.
- **push + trigger**: push before trigger; the trigger dispatches the branch
  head, so it only verifies the fix once the push landed.
- **only trigger**: the trigger row alone.
- **only print**: no row.

The trigger row is the print command without `--print` and without the
redirections: it rebuilds the same line itself, so the line never enters the
row. It MUST carry the same flag and the same `--run` list in the same order,
or it dispatches a different line. Do not add `--workspace`, `--chunk-gate`
or `--apps`: the first run's configuration carries over.
