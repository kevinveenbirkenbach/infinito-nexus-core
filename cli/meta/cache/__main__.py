"""CLI entry: `python -m cli.meta.cache` (run by `make dotenv`)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from utils.cache import pin
from utils.cache.render import render_artifacts
from utils.env.handlers.infinito.cache.conf import KEY, RELATIVE
from utils.env.loader import refresh_from_dotenv

from . import PROJECT_ROOT as REPO_ROOT


def _conf_path() -> Path:
    configured = os.environ.get(KEY, "").strip()
    if configured:
        return Path(configured)
    return REPO_ROOT / RELATIVE


def main(argv: list[str] | None = None) -> int:
    """
    Args:
        argv: command-line arguments; ``--fresh-dotenv PREVIOUS`` names a copy
            of the ``.env`` load.sh sourced before ``make dotenv`` rewrote it,
            and :func:`refresh_from_dotenv` applies the regenerated values
            before the render.

    Returns:
        0 once the files are rendered.
    """
    parser = argparse.ArgumentParser(prog="python -m cli.meta.cache")
    parser.add_argument("--fresh-dotenv", type=Path)
    previous = parser.parse_args([] if argv is None else argv).fresh_dotenv
    if previous is not None:
        refresh_from_dotenv(previous, REPO_ROOT / ".env")
    written = render_artifacts(REPO_ROOT, _conf_path(), pin.served_hosts(os.environ))
    print(
        f"Rendered {len(written)} cache file(s) from the cache: declarations",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
