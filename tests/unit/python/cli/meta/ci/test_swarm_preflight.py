from __future__ import annotations

import io
import tempfile
import unittest
import unittest.mock as mock
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from cli.meta.ci import swarm_preflight
from cli.meta.ci.host_rows import Closure
from cli.meta.ci.swarm_preflight import FLOOR_BYTES, fits, report
from utils.roles.mapping import ROLE_FILE_TASKS_MAIN
from utils.storage.constrained import STORE_ROLE, closure_store_bytes
from utils.tests.swarm.extend_inventory import SWARM_NODES

from . import _host_fixture

_GIB = 2**30
_STORE = 5 * _GIB
_SEEDER = Closure(("web-app-seeder",), {"web-app-seeder": 0})
_HEAVY = Closure(
    ("web-app-bulky", "svc-bkp-vault", "svc-ai-heavy"), {"web-app-bulky": 0}
)
_LIGHT = Closure(("web-app-light", "svc-bkp-vault"), {"web-app-light": 0})


class TestFits(unittest.TestCase):
    def test_closure_above_free_space_does_not_fit(self) -> None:
        self.assertFalse(fits(declared_bytes=50 * _GIB, free_bytes=20 * _GIB))

    def test_floor_alone_can_tip_the_balance(self) -> None:
        self.assertFalse(
            fits(declared_bytes=10 * _GIB, free_bytes=10 * _GIB + FLOOR_BYTES - 1)
        )

    def test_closure_plus_floor_equal_to_free_space_fits(self) -> None:
        self.assertTrue(
            fits(declared_bytes=10 * _GIB, free_bytes=10 * _GIB + FLOOR_BYTES)
        )

    def test_small_closure_fits(self) -> None:
        self.assertTrue(fits(declared_bytes=1 * _GIB, free_bytes=20 * _GIB))


class TestReport(unittest.TestCase):
    def test_roles_are_listed_heaviest_first(self) -> None:
        lines = report(
            "web-app-a#0", {"svc-a": 1, "svc-b": 3}, store_bytes=0, free_bytes=9
        )
        self.assertEqual([line.split()[-1] for line in lines[1:]], ["svc-b", "svc-a"])

    def test_roles_declaring_nothing_are_left_out(self) -> None:
        lines = report(
            "web-app-a#0", {"svc-a": 1, "svc-b": 0}, store_bytes=0, free_bytes=9
        )
        self.assertNotIn("svc-b", "\n".join(lines))

    def test_header_counts_every_closure_role(self) -> None:
        lines = report(
            "web-app-a#0", {"svc-a": 1, "svc-b": 0}, store_bytes=0, free_bytes=9
        )
        self.assertIn("web-app-a#0: 2 roles", lines[0])

    def test_store_copies_lead_the_listing(self) -> None:
        lines = report("web-app-a#0", {"svc-a": 1}, store_bytes=7, free_bytes=9)
        self.assertEqual(lines[1].split()[-2:], [STORE_ROLE, "copies"])


class TestMainOverFixtureRoles(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.roles_dir = Path(self._tmp.name) / "roles"
        _host_fixture.build(self.roles_dir)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run(self, closure: Closure, *, free_bytes: int) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with (
            mock.patch.object(swarm_preflight, "ROLES_DIR", self.roles_dir),
            mock.patch.object(swarm_preflight, "swarm_closure", return_value=closure),
            mock.patch.object(swarm_preflight, "free_space", return_value=free_bytes),
            redirect_stdout(out),
            redirect_stderr(err),
        ):
            rc = swarm_preflight.main(["--app", closure.roles[0], "--variant", "0"])
        return rc, out.getvalue(), err.getvalue()

    def _refused(self, closure: Closure, **free_space: object) -> str:
        with (
            mock.patch.object(swarm_preflight, "ROLES_DIR", self.roles_dir),
            mock.patch.object(swarm_preflight, "swarm_closure", return_value=closure),
            mock.patch.object(swarm_preflight, "free_space", **free_space),
            self.assertRaises(SystemExit) as refused,
        ):
            swarm_preflight.main(["--app", closure.roles[0], "--variant", "0"])
        return str(refused.exception)

    def test_closure_larger_than_free_space_is_refused(self) -> None:
        rc, _out, err = self._run(_HEAVY, free_bytes=20 * _GIB)
        self.assertEqual(rc, 1)
        self.assertIn("REFUSED: web-app-bulky#0", err)

    def test_refusal_names_the_heaviest_role_first(self) -> None:
        _rc, out, _err = self._run(_HEAVY, free_bytes=20 * _GIB)
        self.assertEqual(out.splitlines()[1].split()[-1], "svc-ai-heavy")

    def test_small_closure_passes(self) -> None:
        rc, out, err = self._run(_LIGHT, free_bytes=20 * _GIB)
        self.assertEqual(rc, 0)
        self.assertIn("web-app-light", out)
        self.assertEqual(err, "")

    def test_unreachable_daemon_names_the_bypass(self) -> None:
        message = self._refused(_LIGHT, side_effect=RuntimeError("no daemon"))
        self.assertIn("no daemon", message)
        self.assertIn("preflight=false", message)

    def _seed_store(self) -> None:
        _host_fixture.build_role(
            self.roles_dir,
            STORE_ROLE,
            f"models:\n{_host_fixture.SWARM}  enabled: true\n  min_storage: 5GiB\n",
        )
        _host_fixture.build_role(
            self.roles_dir,
            "web-app-seeder",
            f"seeder:\n{_host_fixture.SWARM}  enabled: true\n  min_storage: 1GiB\n",
        )
        (self.roles_dir / "web-app-seeder" / ROLE_FILE_TASKS_MAIN).parent.mkdir()
        (self.roles_dir / "web-app-seeder" / ROLE_FILE_TASKS_MAIN).write_text(
            f"- ansible.builtin.include_role:\n    name: {STORE_ROLE}\n",
            encoding="utf-8",
        )

    def _store_copies(self, roles: tuple[str, ...]) -> int:
        return closure_store_bytes(
            self.roles_dir, roles, {}, store_nodes=len(SWARM_NODES)
        )

    def test_a_store_consumer_counts_one_store_per_node(self) -> None:
        self._seed_store()
        self.assertEqual(self._store_copies(_SEEDER.roles), len(SWARM_NODES) * _STORE)

    def test_a_listed_store_role_is_counted_once_already(self) -> None:
        self._seed_store()
        self.assertEqual(
            self._store_copies((*_SEEDER.roles, STORE_ROLE)),
            (len(SWARM_NODES) - 1) * _STORE,
        )

    def test_a_closure_without_a_consumer_counts_no_store(self) -> None:
        self._seed_store()
        self.assertEqual(self._store_copies(_LIGHT.roles), 0)

    def test_the_store_copies_refuse_a_closure_its_roles_alone_fit(self) -> None:
        self._seed_store()
        rc, out, err = self._run(_SEEDER, free_bytes=2 * _GIB + FLOOR_BYTES)
        self.assertEqual(rc, 1, out)
        self.assertIn("REFUSED: web-app-seeder#0", err)

    def test_the_closure_fits_once_the_store_copies_fit(self) -> None:
        self._seed_store()
        free = 1 * _GIB + len(SWARM_NODES) * _STORE + FLOOR_BYTES
        rc, _out, err = self._run(_SEEDER, free_bytes=free)
        self.assertEqual(rc, 0, err)

    def test_unparsable_declaration_is_refused_by_name(self) -> None:
        _host_fixture.build_role(
            self.roles_dir,
            "web-app-odd",
            f"odd:\n{_host_fixture.SWARM}  enabled: true\n  min_storage: plenty\n",
        )
        message = self._refused(
            Closure(("web-app-odd",), {"web-app-odd": 0}), return_value=20 * _GIB
        )
        self.assertIn("web-app-odd", message)
        self.assertIn("preflight=false", message)


class TestFreeSpace(unittest.TestCase):
    def _free(self, *, docker_root: int, watchdog_mb: int) -> int:
        with (
            mock.patch.object(
                swarm_preflight,
                "resolved_docker_root_free_bytes",
                return_value=docker_root,
            ),
            mock.patch.object(
                swarm_preflight, "lowest_free_mb", return_value=(watchdog_mb, "/")
            ),
        ):
            return swarm_preflight.free_space()

    def test_a_fuller_watchdog_root_wins(self) -> None:
        self.assertEqual(self._free(docker_root=50 * _GIB, watchdog_mb=10), 10 * 2**20)

    def test_a_fuller_docker_root_wins(self) -> None:
        self.assertEqual(self._free(docker_root=5, watchdog_mb=10), 5)

    def test_a_docker_root_that_cannot_be_measured_fails_closed(self) -> None:
        with (
            mock.patch.object(
                swarm_preflight,
                "resolved_docker_root_free_bytes",
                side_effect=RuntimeError("remote daemon"),
            ),
            self.assertRaises(RuntimeError),
        ):
            swarm_preflight.free_space()


if __name__ == "__main__":
    unittest.main()
