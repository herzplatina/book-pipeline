"""End-to-end integration test for the Book Pipeline CI workflow.

Rather than asserting that the workflow file contains particular values, this
drives the workflow the way GitHub does: it reads the real step definitions,
executes the commands they declare, and checks the product actually does what
the workflow exists to make it do -- run a full discover/score/enrich/dispatch
pass and leave run reports where the upload step collects them.

The scheduled runs on 2026-07-13/20/27 failed at the "Run checks" step, which
is executed here for real.
"""

import json
import re
import shlex
import subprocess
import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

import pipeline
from config.settings import CLAUDE_SCORE_THRESHOLD

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "book-pipeline.yml"

# `${{ a || b || 'literal' }}` -- GitHub falls through to the quoted literal
# when no input or repo variable is set, which is the scheduled-run case.
EXPRESSION = re.compile(r"\$\{\{[^}]*?'([^']*)'[^}]*?\}\}")

# A `NAME="value"` assignment line inside a `run:` block.
ASSIGNMENT = re.compile(r'^(?P<name>[A-Za-z_][A-Za-z0-9_]*)="?(?P<value>.*?)"?$')


def _steps():
    """Return the workflow's steps, keyed by step name."""
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["run-pipeline"]["steps"]
    return {step["name"]: step for step in steps if "name" in step}


def _commands(step_name):
    """Shell commands from a step's `run:` block, as the runner would see them.

    Resolves the two things bash does before the command executes: `${{ }}`
    expressions fall through to their quoted default, and `NAME=value` lines
    are substituted into the commands that reference `$NAME`.
    """
    run_block = _steps()[step_name]["run"]
    resolved = EXPRESSION.sub(lambda m: m.group(1), run_block)

    variables: dict[str, str] = {}
    commands = []
    for line in (raw.strip() for raw in resolved.splitlines()):
        if not line:
            continue
        assignment = ASSIGNMENT.match(line)
        if assignment and " " not in assignment.group("name"):
            variables[assignment.group("name")] = assignment.group("value")
            continue
        for name, value in variables.items():
            line = line.replace(f'"${name}"', value).replace(f"${name}", value)
        commands.append(line)
    return commands


def _as_argv(command):
    """Split a command, pointing `python` at the interpreter running the tests."""
    argv = shlex.split(command)
    if argv and argv[0] in ("python", "python3"):
        argv[0] = sys.executable
    return argv


@pytest.fixture
def stubbed_externals():
    """Stub every network boundary so a full run can complete offline.

    Everything inside pipeline.run() -- staging, filtering, routing, counting
    and report writing -- is the real implementation.
    """
    lead = {
        "Archetype": "health",
        "Source": "youtube",
        "Source URL": "https://youtu.be/example",
        "Channel URL": "https://www.youtube.com/channel/channel_123",
        "Status": "New",
        "_content": "Told a full transformation story.",
    }
    scored = {
        **lead,
        "Claude Score": CLAUDE_SCORE_THRESHOLD,
        "_archetype_match": True,
        "_disposition": "auto",
    }

    airtable = MagicMock()
    with ExitStack() as stack:
        stack.enter_context(patch("pipeline.get_client", return_value=airtable))
        stack.enter_context(patch("pipeline.score", return_value=scored))
        stack.enter_context(patch("pipeline.enrich"))
        stack.enter_context(patch("pipeline.send_run_report"))
        stack.enter_context(
            patch(
                "pipeline.dispatch",
                side_effect=lambda ld, **kw: ld.update(
                    _outreach_decision="hunter_sequence"
                ),
            )
        )
        discover = {
            name: stack.enter_context(
                patch.object(
                    module,
                    "discover",
                    return_value=[dict(lead)] if name == "youtube" else [],
                )
            )
            for name, module in pipeline.MODULES.items()
        }
        yield {"airtable": airtable, "discover": discover}


def test_ci_check_commands_succeed():
    """The "Run checks" step must pass against the repo as committed.

    This is the step that actually turned the scheduled runs red.
    """
    for command in _commands("Run checks"):
        if "pytest" in command:
            # Executing the suite from inside the suite would recurse; pytest
            # is already proving itself by running this test.
            continue

        argv = _as_argv(command)
        try:
            result = subprocess.run(
                argv,
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            raise AssertionError(
                f"`{argv[0]}` is not installed, so the CI step `{command}` "
                f"cannot be verified. Install it with the same command the "
                f"workflow uses: `pip install ruff pytest pyyaml`."
            ) from None
        assert result.returncode == 0, (
            f"CI would fail on `{command}`:\n{result.stdout}{result.stderr}"
        )


def test_pipeline_step_runs_end_to_end_and_reports_its_work(
    stubbed_externals, tmp_path
):
    """The workflow's own pipeline command drives a full run and summarises it."""
    command = next(c for c in _commands("Run pipeline") if "pipeline.py" in c)
    argv = _as_argv(command)[2:]  # drop the interpreter and pipeline.py
    args = pipeline._parse_args(argv)

    summary = pipeline.run(
        args.modules,
        report_dir=tmp_path,
        no_dispatch=args.no_dispatch,
    )

    # Every module the workflow asks for is actually queried.
    for name in args.modules:
        stubbed_externals["discover"][name].assert_called_once()

    # A qualifying lead completes the whole path: scored, routed, and upserted.
    assert summary["discovered"] == 1
    assert summary["qualifying"] == 1
    assert summary["dispatched"] == 1
    assert summary["errors"] == 0
    stubbed_externals["airtable"].upsert.assert_called_once()


def test_pipeline_step_leaves_artifacts_where_the_upload_step_collects_them(
    stubbed_externals, tmp_path
):
    """The run reports must land in the directory the upload step globs.

    A mismatch here uploads nothing and silently loses the record of a run.
    """
    command = next(c for c in _commands("Run pipeline") if "pipeline.py" in c)
    args = pipeline._parse_args(_as_argv(command)[2:])
    upload_path = _steps()["Upload run reports"]["with"]["path"]

    assert Path(args.report_dir) == Path(upload_path), (
        f"pipeline writes to {args.report_dir!r} but the upload step collects "
        f"{upload_path!r}; artifacts would never be uploaded"
    )

    # Run against a temp dir so the test never writes into the repo.
    pipeline.run(args.modules, report_dir=tmp_path, no_dispatch=args.no_dispatch)

    summary_file = _only(tmp_path, "*-summary.json")
    payload = json.loads(summary_file.read_text(encoding="utf-8"))
    assert payload["summary"]["qualifying"] == 1
    assert payload["errors"] == []

    qualified = json.loads(
        _only(tmp_path, "*-qualified-leads.json").read_text(encoding="utf-8")
    )
    assert [entry["source_url"] for entry in qualified] == ["https://youtu.be/example"]

    assert "No errors recorded." in _only(tmp_path, "*-errors.log").read_text(
        encoding="utf-8"
    )


def _only(directory, pattern):
    """Return the single file matching pattern, asserting there is exactly one."""
    matches = list(directory.glob(pattern))
    assert len(matches) == 1, f"expected exactly one {pattern}, found {matches}"
    return matches[0]
