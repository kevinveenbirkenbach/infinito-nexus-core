import unittest

from utils.cache.files import PROJECT_ROOT, read_text
from utils.cache.yaml import load_yaml_str
from utils.roles.mapping import ROLE_FILE_VARS_MAIN

ROLE = PROJECT_ROOT / "roles" / "web-app-mobilizon"
PROGRAMS = ("account.exs", "design.exs", "rbac.exs")
PROBE_TASK_FILES = ("01_design.yml", "02_reload_design.yml")
READY = "mobilizon_rpc_ready"
PROBE_EXPRESSION = 'IO.puts("{{ ' + READY + ' }}")'


def exits_fail_the_rpc(program):
    """Args:
        program: the text of an Elixir program run through ``mobilizon rpc``.

    Returns:
        Whether every statement after the log level runs inside a try whose exits raise.
    """
    lines = [line for line in program.splitlines() if line.strip()]
    body = lines[1:]
    if not body or "catch" not in body:
        return False
    catch = body.index("catch")
    return (
        body[0] == "try do"
        and body[-1] == "end"
        and body[catch + 1].strip().startswith(":exit, reason -> raise ")
        and all(line.startswith("  ") for line in body[1:catch])
    )


def rpc_probes(tasks):
    """Args:
        tasks: the parsed entries of a task file.

    Returns:
        Every task that runs a one-line ``IO.puts`` through ``mobilizon rpc``.
    """
    probes = []
    for task in tasks:
        command = task.get("ansible.builtin.command")
        argv = command.get("argv", []) if isinstance(command, dict) else []
        if "rpc" in argv and str(argv[-1]).startswith("IO.puts("):
            probes.append(task)
    return probes


def probe_requires_marker(task):
    """Args:
        task: a task returned by ``rpc_probes``.

    Returns:
        Whether the probe prints the ready marker and waits for it on stdout, not only for exit code 0.
    """
    result = task["register"]
    return (
        task["ansible.builtin.command"]["argv"][-1] == PROBE_EXPRESSION
        and task["until"] == f"{result}.rc == 0 and {READY} in {result}.stdout_lines"
    )


class TestRpcProgramsFailOnExit(unittest.TestCase):
    def test_every_program_raises_on_an_exit(self):  # nocheck: test.text-presence -- asserts Elixir that runs only inside the app container; no Elixir runner yet  # fmt: skip
        for name in PROGRAMS:
            with self.subTest(program=name):
                program = read_text(str(ROLE / "files" / "elixir" / name))
                self.assertTrue(exits_fail_the_rpc(program))

    def test_an_unguarded_program_is_rejected(self):
        self.assertFalse(
            exits_fail_the_rpc(
                "Logger.put_process_level(self(), :error)\n"
                'IO.puts("MOBILIZON_RBAC=done")\n'
            )
        )

    def test_a_program_that_swallows_the_exit_is_rejected(self):
        self.assertFalse(
            exits_fail_the_rpc(
                "Logger.put_process_level(self(), :error)\n"
                "try do\n"
                '  IO.puts("MOBILIZON_RBAC=done")\n'
                "catch\n"
                "  :exit, reason -> reason\n"
                "end\n"
            )
        )


class TestRpcProbesRequireMarker(unittest.TestCase):
    def test_the_ready_marker_is_defined_once(self):
        variables = load_yaml_str(read_text(str(ROLE / ROLE_FILE_VARS_MAIN)))
        self.assertEqual(variables[READY], "MOBILIZON_RPC=ready")

    def test_every_probe_waits_for_the_marker(self):
        for name in PROBE_TASK_FILES:
            tasks = load_yaml_str(read_text(str(ROLE / "tasks" / name)))
            probes = rpc_probes(tasks)
            with self.subTest(tasks=name):
                self.assertEqual(len(probes), 1)
                self.assertTrue(probe_requires_marker(probes[0]))

    def test_a_probe_that_checks_only_the_exit_code_is_rejected(self):
        probe = {
            "ansible.builtin.command": {"argv": ["container", "rpc", "IO.puts(:ok)"]},
            "register": "probe",
            "until": "probe.rc == 0",
        }
        self.assertEqual(rpc_probes([probe]), [probe])
        self.assertFalse(probe_requires_marker(probe))

    def test_a_probe_without_the_printed_marker_is_rejected(self):
        probe = {
            "ansible.builtin.command": {"argv": ["container", "rpc", "IO.puts(:ok)"]},
            "register": "probe",
            "until": f"probe.rc == 0 and {READY} in probe.stdout_lines",
        }
        self.assertFalse(probe_requires_marker(probe))


if __name__ == "__main__":
    unittest.main()
