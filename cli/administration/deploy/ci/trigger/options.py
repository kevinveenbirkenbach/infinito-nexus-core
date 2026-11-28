from __future__ import annotations

import argparse

_FAILED_ONLY = {
    "strict": "--strict",
    "roles_only": "--roles-only",
    "any_axes": "--any-axes",
    "print_only": "--print",
}
_REFUSALS = (
    (
        lambda args: args.any_axes and (args.strict or args.roles_only),
        "--any-axes cannot be combined with --strict or --roles-only",
    ),
    (
        lambda args: args.priority is not None and args.failed is not None,
        "--priority and --failed both build the priority line",
    ),
    (
        lambda args: len(args.runs or ()) > 1 and args.failed is None,
        "--run is repeatable only with --failed",
    ),
    (
        lambda args: any(not ref.strip() for ref in args.runs or ()),
        "--run was empty",
    ),
    (
        lambda args: args.apps is not None and not args.apps.split(),
        "--apps was empty",
    ),
    (
        lambda args: args.priority is not None and not args.priority.split(),
        "--priority was empty",
    ),
)


def _arg(*flags: str, **spec: object) -> tuple[tuple[str, ...], dict[str, object]]:
    """Args:
    flags: the option strings.
    spec: the keywords ``add_argument`` takes.
    """
    return flags, spec


_SOURCE_ARGUMENTS = (
    _arg(
        "--failed",
        nargs="?",
        const=True,
        default=None,
        metavar="(ignored)",
        help=(
            "Re-trigger what was not green in the source run as the priority "
            "line, together with the priority entries that run never deployed "
            "at all; the remaining roles follow once they succeed, starting "
            "behind the green stretch the run added to the offset it was "
            "given. Every mode is read, and each failed job comes back as the "
            "exact selection that failed -- variant, deploy mode and onion "
            "state included. A leftover scope argument is accepted and "
            "ignored."
        ),
    ),
    _arg(
        "--apps",
        default=None,
        metavar='"app1 app2 ..."',
        help="Explicit space-separated role ids to trigger.",
    ),
)
_ARGUMENTS = (
    _arg(
        "--run",
        dest="runs",
        action="append",
        default=None,
        metavar="URL|ID",
        help=(
            "Run URL or bare run id to reproduce: its configuration (distros, "
            "mode, lifecycles, filesystem, architectures, chunk_gate, "
            "workspace, instructions) is carried over, and with --failed its "
            "results also pick the apps. A bare id resolves against the current "
            "branch's repo. With --failed and no --run: the latest deploy run "
            "on the current branch. Repeatable with --failed: the priority "
            "line is the union of every run's failed selections, while the "
            "configuration and the offset come from the first --run. The "
            "dispatch always targets the current branch's repo."
        ),
    ),
    _arg(
        "--strict",
        action="store_true",
        help=(
            "With --failed: re-trigger only roles with a hard failure (❌), "
            "not cancelled/aborted (🚫) or still-running (⏳). Those two never "
            "reached a verdict, so the regular line owes them their turn "
            "rather than the priority line owing them a place."
        ),
    ),
    _arg(
        "--roles-only",
        action="store_true",
        help=(
            "With --failed: put the roles that failed outright on the priority "
            "line by name, letting the rotation assign the axes, instead of "
            "replaying the exact combination each job failed in. Useful when "
            "so much is red that covering the role matters more than "
            "reproducing the row. Only a hard failure collapses: without "
            "--strict a cancelled or still-running job comes back as the exact "
            "combination it never finished, and a priority entry the source "
            "run never deployed keeps its pins either way -- that run holds no "
            "evidence against the axes they named."
        ),
    ),
    _arg(
        "--any-axes",
        action="store_true",
        help=(
            "With --failed: put every role that did not come out green on the "
            "priority line by name -- hard failures (❌), cancelled or aborted "
            "(🚫) and still-running (⏳) jobs alike -- together with the "
            "priority entries the source run never deployed, their pins "
            "dropped too. Like any bare priority entry, each role then runs "
            "in every variant and in every deploy mode, network and mesh "
            "state the run offers, while distro, filesystem and architecture "
            "rotate afresh; a cancelled run can therefore fan out to more "
            "chunk blocks than call-orchestrator.yml declares, which the "
            "planner refuses. A green role stays off the priority line. "
            "Cannot be combined with --strict, "
            "which would leave the unfinished roles out, or --roles-only, "
            "which this already covers."
        ),
    ),
    _arg(
        "--print",
        dest="print_only",
        action="store_true",
        help=(
            "With --failed: print the priority line the retrigger would "
            "dispatch, its tokens separated by single spaces, and exit "
            "without dispatching. The line is ready to paste into the "
            "priority input of a manual dispatch. stderr carries the "
            "summary: tokens per source run, the union, the priority rows "
            "the planner would plan for it, the offset and the carried "
            "configuration. The line is validated offline first. stdout "
            "holds the line only on exit 0; otherwise it stays empty and the "
            "status says why: 1 a token cannot deploy on the branch, 2 an "
            "argument error, 3 nothing failed, 4 the planner aborted on the "
            "line, 5 no deploy run was found, 6 a source run could not be "
            "read (a gh call failed or the URL is malformed)."
        ),
    ),
    _arg(
        "--chunk-gate",
        choices=("true", "false"),
        default=None,
        help=(
            "Override the carried chunk_gate input. 'false' keeps deploying "
            "the remaining chunks after a failed one instead of stopping the "
            "chain; 'true' stops at the first failed chunk. Omitted: the "
            "source run's value, else the workflow default."
        ),
    ),
    _arg(
        "--priority",
        default=None,
        metavar='"role#0@compose+clearnet%debian ..."',
        help=(
            "Lead the run with these selection tokens. Unlike --failed, which "
            "derives them from a run's verdicts, this states them: a "
            "verification run names the combination it wants to see, axis by "
            "axis. Composes with --apps; --failed builds its own line."
        ),
    ),
    _arg(
        "--workspace",
        choices=("auto", "true", "false"),
        default=None,
        help=(
            "Override the carried workspace input. 'false' leaves the "
            "workspace test out, which a run that only has to reach a deploy "
            "verdict does not need."
        ),
    ),
    _arg(
        "--mode",
        choices=("auto", "host", "compose", "swarm"),
        default=None,
        help="Override the carried deploy mode pool.",
    ),
    _arg(
        "--tor",
        choices=("auto", "enforced", "exclusive", "disabled"),
        default=None,
        help="Override the carried tor axis.",
    ),
    _arg(
        "--distros",
        default=None,
        metavar='"debian arch"',
        help="Override the carried distro pool.",
    ),
    _arg(
        "--filesystem",
        default=None,
        metavar='"ext4 btrfs"',
        help=(
            "Override the carried filesystem pool. A pool of exactly one is a "
            "human naming the kind, so a host whose kernel cannot serve it "
            "fails the row instead of substituting one."
        ),
    ),
)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="infinito administration deploy ci trigger",
        description=(
            "Dispatch the manual CI workflow for the branch you are on. "
            "Default: trigger every role. With --failed: the roles that "
            "failed in the last run form the priority line and the full "
            "run follows once they are green. With --apps: an explicit "
            "role list as whitelist. Whenever a source run is read, its "
            "configuration is carried over so the retrigger reproduces it."
        ),
    )
    group = p.add_mutually_exclusive_group()
    for flags, spec in _SOURCE_ARGUMENTS:
        group.add_argument(*flags, **spec)
    for flags, spec in _ARGUMENTS:
        p.add_argument(*flags, **spec)
    return p


def check(p: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Args:
    p: the parser whose ``error`` exits with status 2.
    args: the parsed arguments.
    """
    refusals = [
        f"{flag} only applies with --failed"
        for name, flag in _FAILED_ONLY.items()
        if getattr(args, name) and args.failed is None
    ]
    refusals += [message for refused, message in _REFUSALS if refused(args)]
    if refusals:
        p.error(refusals[0])
