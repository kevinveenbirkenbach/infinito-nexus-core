from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import ClassVar
from unittest.mock import patch

import cli.meta.env.__main__ as env_main
from utils.cache.files import PROJECT_ROOT, read_text
from utils.env.handlers.infinito.cache.conf import KEY as CONF_KEY
from utils.env.parser import parse_static_env

KEY = "INFINITO_TOOLS_MODELS_MAX_SIZE"
NEW = "13579m"
EXPORTED = "2468m"
CUSTOM = "97531m"
PREVIOUS = "@previous"
LOADER_DIR = Path(PROJECT_ROOT) / "scripts" / "meta" / "env"
CACHE_PROBE = """
import os, sys
from pathlib import Path
from unittest.mock import patch
import cli.meta.cache.__main__ as cache_main

def render(*_args, **_kwargs):
    print(os.environ.get(sys.argv[2], ""))
    return []

with (
    patch.object(cache_main, "REPO_ROOT", Path(sys.argv[1])),
    patch.object(cache_main, "render_artifacts", render),
    patch.object(cache_main.pin, "served_hosts", return_value=set()),
):
    sys.exit(cache_main.main(sys.argv[3:]))
"""


def clean_env() -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("INFINITO_")
        and k not in ("BASH_ENV", "PYTHONPATH", "VENV", "PYTHON", "VIRTUAL_ENV")
    }
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    return env


class TestRegenerateInPlace(unittest.TestCase):
    old_dotenv: ClassVar[Path]
    scratch: ClassVar[Path]

    @classmethod
    def setUpClass(cls) -> None:
        cls.scratch = Path(tempfile.mkdtemp())
        cls.old_dotenv = cls.scratch / "old.env"
        subprocess.run(
            [sys.executable, "-m", "cli.meta.env", "--output", str(cls.old_dotenv)],
            env=clean_env(),
            cwd=PROJECT_ROOT,
            capture_output=True,
            check=True,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.scratch)

    def old(self, key: str = KEY) -> str:
        """
        Args:
            key: the variable looked up.

        Returns:
            The value the checkout's `.env` holds for *key* before the regeneration.
        """
        return parse_static_env(self.old_dotenv)[key]

    def regenerate(
        self,
        steps: str,
        custom: str = "",
        cache_argv: list[str] | None = None,
        key: str = KEY,
    ) -> str:
        """
        Args:
            steps: bash run in the checkout before the generator; ``load``
                sources the loader, as BASH_ENV does for every recipe.
            custom: the content of the checkout's custom.env, empty for none.
            cache_argv: when given, the arguments of the cache render that
                runs next in the same recipe env, as `make dotenv` does;
                PREVIOUS stands for the copy of `.env` the recipe takes first.
            key: the variable reported.

        Returns:
            The value the regenerated `.env` holds for *key*, or with
            *cache_argv* the value the cache render sees.
        """
        self.assertNotIn(self.old(), (NEW, EXPORTED, CUSTOM))
        checkout = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, checkout)
        (checkout / "scripts" / "meta" / "env").mkdir(parents=True)
        for name in ("load.sh", "python.sh"):
            shutil.copy(LOADER_DIR / name, checkout / "scripts" / "meta" / "env")
        shutil.copy(self.old_dotenv, checkout / ".env")
        shutil.copy(self.old_dotenv, checkout / "previous.env")
        default = read_text(str(Path(PROJECT_ROOT) / "default.env"))
        self.assertIn(f"\n{KEY}={self.old()}\n", default)
        (checkout / "default.env").write_text(
            default.replace(f"\n{KEY}={self.old()}\n", f"\n{KEY}={NEW}\n"),
            encoding="utf-8",
        )
        if custom:
            (checkout / "custom.env").write_text(custom, encoding="utf-8")
        proc = subprocess.run(
            [
                "bash",
                "-c",
                f"load() {{ source scripts/meta/env/load.sh; }}\n{steps}\nenv -0",
            ],
            env=clean_env(),
            cwd=checkout,
            capture_output=True,
            check=True,
        )
        recipe_env = dict(
            entry.split("=", 1)
            for entry in proc.stdout.decode("utf-8").split("\0")
            if "=" in entry
        )
        with (
            patch.object(env_main, "REPO_ROOT", checkout),
            patch.dict(os.environ, recipe_env, clear=True),
        ):
            self.assertEqual(env_main.main([]), 0)
        if cache_argv is not None:
            argv = [
                str(checkout / "previous.env") if arg == PREVIOUS else arg
                for arg in cache_argv
            ]
            probe = subprocess.run(
                [sys.executable, "-c", CACHE_PROBE, str(checkout), key, *argv],
                env={**recipe_env, "PYTHONPATH": str(PROJECT_ROOT)},
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                check=True,
            )
            return probe.stdout.strip()
        written = (checkout / ".env").read_text(encoding="utf-8")  # nocheck: cache-read
        return next(
            line.split("=", 1)[1]
            for line in written.splitlines()
            if line.startswith(f"{key}=")
        )

    def test_a_value_only_the_old_dotenv_carried_follows_the_new_default(self) -> None:
        self.assertEqual(self.regenerate("load"), NEW)

    def test_an_exported_value_wins(self) -> None:
        self.assertEqual(self.regenerate(f"export {KEY}={EXPORTED}\nload"), EXPORTED)

    def test_an_export_equal_to_the_old_value_wins(self) -> None:
        self.assertEqual(
            self.regenerate(f"export {KEY}={self.old()}\nload"), self.old()
        )

    def test_a_value_exported_after_the_load_wins(self) -> None:
        self.assertEqual(
            self.regenerate(f"load\nexport {KEY}={EXPORTED}\nload"), EXPORTED
        )

    def test_a_custom_env_value_wins(self) -> None:
        self.assertEqual(self.regenerate("load", f"{KEY}={CUSTOM}\n"), CUSTOM)

    def test_the_cache_render_of_make_dotenv_sees_the_regenerated_value(self) -> None:
        self.assertEqual(
            self.regenerate("load", cache_argv=["--fresh-dotenv", PREVIOUS]), NEW
        )

    def test_the_cache_render_keeps_an_exported_value(self) -> None:
        self.assertEqual(
            self.regenerate(
                f"export {KEY}={EXPORTED}\nload",
                cache_argv=["--fresh-dotenv", PREVIOUS],
            ),
            EXPORTED,
        )

    def test_the_cache_render_keeps_a_value_exported_after_the_load(self) -> None:
        self.assertEqual(
            self.regenerate(
                f"load\nexport {KEY}={EXPORTED}\nload",
                cache_argv=["--fresh-dotenv", PREVIOUS],
            ),
            EXPORTED,
        )

    def test_the_cache_render_keeps_a_run_fact_exported_after_the_load(self) -> None:
        self.assertNotEqual(self.old(CONF_KEY), "/caller/upstreams.conf")
        self.assertEqual(
            self.regenerate(
                f"load\nexport {CONF_KEY}=/caller/upstreams.conf\nload",
                cache_argv=["--fresh-dotenv", PREVIOUS],
                key=CONF_KEY,
            ),
            "/caller/upstreams.conf",
        )

    def test_the_cache_render_keeps_a_host_owned_dotenv(self) -> None:
        self.assertEqual(
            self.regenerate(
                "export INFINITO_DOTENV_HOST_OWNED=true\nload",
                cache_argv=["--fresh-dotenv", PREVIOUS],
            ),
            self.old(),
        )

    def test_a_cache_render_without_the_flag_keeps_the_process_env(self) -> None:
        self.assertEqual(self.regenerate("load", cache_argv=[]), self.old())


if __name__ == "__main__":
    unittest.main()
