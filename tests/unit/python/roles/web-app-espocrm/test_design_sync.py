import base64
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from utils import PROJECT_ROOT
from utils.cache.files import read_text

SCRIPT = PROJECT_ROOT / "roles/web-app-espocrm/files/shell/design_sync.sh"
APP_ROOT = "cd /var/www/html"
FAILURE = "Error: Error while clearing cache."

STUB_PHP = """#!{python}
import json, os, sys
args = sys.argv[2:]
with open(os.environ["STUB_LOG"], "a") as log:
    log.write(json.dumps(args) + "\\n")
if args[0] == os.environ["STUB_FAIL"]:
    print(os.environ["STUB_FAILURE"])
    sys.exit(1)
if args[0] == "config:get":
    print({{"theme": "Espo", "applicationName": "EspoCRM"}}[args[1]])
"""


class TestDesignSync(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.app = root / "html"
        self.app.mkdir()
        self.log = root / "calls.jsonl"
        self.log.touch()
        self.bin = root / "bin"
        self.bin.mkdir()
        stub = self.bin / "php"
        stub.write_text(STUB_PHP.format(python=sys.executable))
        stub.chmod(0o755)
        script = read_text(str(SCRIPT))
        self.assertIn(APP_ROOT, script)
        self.script = script.replace(APP_ROOT, f"cd {self.app}")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run(self, fail: str) -> subprocess.CompletedProcess[str]:
        payload = "".join(
            f"{path} {base64.b64encode(content.encode()).decode()}\n"
            for path, content in (
                ("module/Resources/module.json", '{"order": 100}'),
                ("assets/theme.css", "body{}"),
                ("assets/title", "Infinito"),
            )
        )
        return subprocess.run(
            [
                "sh",
                "-c",
                self.script,
                "design_sync",
                "present",
                "Infinito",
                "Infinito",
                "custom/Espo/Modules/InfinitoDesign",
                "client/custom/infinito-design",
            ],
            input=payload,
            capture_output=True,
            text=True,
            env={
                "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
                "STUB_LOG": str(self.log),
                "STUB_FAIL": fail,
                "STUB_FAILURE": FAILURE,
            },
            check=False,
        )

    def _commands(self) -> list[str]:
        return [
            json.loads(line)[0]
            for line in self.log.read_text().splitlines()  # nocheck: cache-read tempdir fixture
        ]

    def test_first_present_run_applies_theme_and_title(self) -> None:
        result = self._run("")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "CHANGED")
        self.assertEqual(
            self._commands(),
            [
                "config:get",
                "config:set",
                "config:get",
                "config:set",
                "clear-cache",
                "update-app-timestamp",
            ],
        )

    def test_failing_cache_clear_names_the_command_and_its_message(self) -> None:
        result = self._run("clear-cache")

        self.assertEqual(result.returncode, 1)
        self.assertIn("command.php clear-cache exited 1", result.stderr)
        self.assertIn(FAILURE, result.stderr)
        self.assertNotIn("update-app-timestamp", self._commands())

    def test_failing_config_read_names_the_command_and_its_message(self) -> None:
        result = self._run("config:get")

        self.assertEqual(result.returncode, 1)
        self.assertIn("command.php config:get exited 1", result.stderr)
        self.assertIn(FAILURE, result.stderr)
        self.assertEqual(self._commands(), ["config:get"])

    def test_failing_config_write_names_the_command_and_its_message(self) -> None:
        result = self._run("config:set")

        self.assertEqual(result.returncode, 1)
        self.assertIn("command.php config:set exited 1", result.stderr)
        self.assertIn(FAILURE, result.stderr)


if __name__ == "__main__":
    unittest.main()
