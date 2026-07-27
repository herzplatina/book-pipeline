"""Tests guarding the GitHub Actions workflow definitions.

These protect against a regression that broke CI: actions pinned to majors
that still declare `runs.using: node20`, which GitHub now forces onto the
Node.js 24 runtime and reports as a deprecation.
"""

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
DEPENDABOT_CONFIG = REPO_ROOT / ".github" / "dependabot.yml"

# First major version of each action whose action.yml declares
# `runs.using: node24`. Verified against the upstream action.yml, not the
# release notes -- upload-artifact@v5 advertises Node 24 support but still
# declares node20, so v6 is the real floor.
MINIMUM_ACTION_MAJORS = {
    "actions/checkout": 5,
    "actions/setup-python": 6,
    "actions/upload-artifact": 6,
}

MAJOR_VERSION_PATTERN = re.compile(r"^v(\d+)")


def _iter_uses_refs(node):
    """Yield every `uses:` string in a parsed workflow, at any nesting depth."""
    if isinstance(node, dict):
        used = node.get("uses")
        if isinstance(used, str):
            yield used
        for value in node.values():
            yield from _iter_uses_refs(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_uses_refs(item)


def _workflow_files():
    return sorted(WORKFLOW_DIR.glob("*.yml")) + sorted(WORKFLOW_DIR.glob("*.yaml"))


def _external_action_refs():
    """Return (workflow_name, action, ref) for each third-party action used."""
    refs = []
    for workflow in _workflow_files():
        parsed = yaml.safe_load(workflow.read_text())
        for used in _iter_uses_refs(parsed):
            # Local composite actions and container actions carry no pinned
            # major version, so the Node runtime policy does not apply.
            if used.startswith((".", "docker://")):
                continue
            action, _, ref = used.partition("@")
            refs.append((workflow.name, action, ref))
    return refs


def test_workflow_directory_is_present_and_parses():
    workflows = _workflow_files()
    assert workflows, "expected at least one workflow under .github/workflows"
    for workflow in workflows:
        assert yaml.safe_load(workflow.read_text()) is not None


def test_actions_are_pinned_to_a_node24_major():
    """The direct regression test for the Node.js 20 deprecation failure."""
    violations = []
    for workflow_name, action, ref in _external_action_refs():
        minimum = MINIMUM_ACTION_MAJORS.get(action)
        if minimum is None:
            continue

        match = MAJOR_VERSION_PATTERN.match(ref)
        assert match, (
            f"{workflow_name}: {action} is pinned to {ref!r}, which has no "
            f"readable major version. Pin it to a vN tag so the Node runtime "
            f"can be verified."
        )

        major = int(match.group(1))
        if major < minimum:
            violations.append(
                f"{workflow_name}: {action}@{ref} runs on Node.js 20; "
                f"v{minimum} or newer is required"
            )

    assert not violations, "Actions on a deprecated Node runtime:\n" + "\n".join(
        violations
    )


def test_every_action_has_a_declared_minimum_major():
    """A new action must be added to the policy, so it cannot silently rot."""
    unknown = {
        f"{action} (in {workflow_name})"
        for workflow_name, action, _ in _external_action_refs()
        if action not in MINIMUM_ACTION_MAJORS
    }

    assert not unknown, (
        "These actions have no entry in MINIMUM_ACTION_MAJORS. Check the "
        "`runs.using:` runtime in their action.yml and record the first "
        "major that targets the current Node runtime:\n" + "\n".join(sorted(unknown))
    )


def test_dependabot_watches_github_actions():
    """Keeps action majors moving so the next deprecation arrives as a PR."""
    assert DEPENDABOT_CONFIG.exists(), (
        f"expected a Dependabot config at {DEPENDABOT_CONFIG.relative_to(REPO_ROOT)}"
    )

    config = yaml.safe_load(DEPENDABOT_CONFIG.read_text())
    ecosystems = {
        update.get("package-ecosystem") for update in config.get("updates", [])
    }

    assert "github-actions" in ecosystems, (
        "Dependabot must track the github-actions ecosystem so action majors "
        "are upgraded before their Node runtime is deprecated"
    )
