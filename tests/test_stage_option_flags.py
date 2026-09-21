"""Every option a stage registers must be a flag the CLI actually accepts.

This is the bug that keeps happening. The re-encoder shipped with the studio
asking for `format` while the stage answered to `texture-format`; the argument
parser refused the whole run, and nothing found it until somebody watched a
live job fail. The cull shipped with four options the CLI had no flags for at
all, which would have failed the same way.

Both are the same shape: a name registered in one place and spelled in another,
with nothing comparing the two. So here they are, compared.
"""

from __future__ import annotations

import argparse

from reference_asset_compiler.cli import build_parser
from reference_asset_compiler.stages import STAGES


def cli_flags() -> set[str]:
    """Every long flag `rac run-stage` accepts, without its dashes."""
    parser = build_parser()
    for action in parser._actions:  # noqa: SLF001 -- argparse offers no public walk
        if not isinstance(action, argparse._SubParsersAction):  # noqa: SLF001
            continue
        stage = action.choices.get("run-stage")
        if stage is None:
            continue
        return {option.lstrip("-").replace("-", "_")
                for candidate in stage._actions  # noqa: SLF001
                for option in candidate.option_strings
                if option.startswith("--")}
    raise AssertionError("rac has no run-stage command any more")


def test_every_registered_option_is_a_flag_the_cli_accepts():
    flags = cli_flags()
    missing = {
        name: stage
        for stage, definition in STAGES.items()
        for name in definition.get("options", ())
        if name not in flags
    }
    assert not missing, (
        "These options are registered on a stage but no flag reaches them, so a caller "
        "naming one has its whole run refused by the argument parser: {0}".format(missing))
