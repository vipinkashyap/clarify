"""Clarify CLI.

Top-level Typer app; commands live in submodules grouped by what they do:

  cli.extract  — fetch, ingest, ingest-plain, build-claims, prompt
  cli.serve    — bootstrap, build-static
  cli.inspect  — list, info, stats

Each submodule registers its commands on `app` at import time.
"""

from __future__ import annotations

import typer

app = typer.Typer(
    add_completion=False,
    help="Clarify — single-paper claim extractor + reading overlay.",
    no_args_is_help=True,
)

# Importing for side effects: each module registers commands on `app`.
from clarify.cli import extract as _extract  # noqa: E402,F401
from clarify.cli import serve as _serve  # noqa: E402,F401
from clarify.cli import inspect as _inspect  # noqa: E402,F401


if __name__ == "__main__":
    app()
