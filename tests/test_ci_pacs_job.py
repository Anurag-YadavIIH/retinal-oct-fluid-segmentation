"""TC-135 — CI runs the PACS round-trip against an ephemeral, loopback-only Orthanc.

Traces to: SRS-094; `docs/06` §7.2.1

`docs/06` §7.2.1 permits objects to leave the local Orthanc instance for exactly one
destination: an Orthanc started for a single CI job, under conditions it lists. Those
conditions live in `.github/workflows/ci.yml`, where nothing would notice them change. This
test reads the workflow and checks each one, so the amendment's conditions are checked
rather than claimed.

**It inspects the mechanism, and is shown able to fail** (`docs/07` §3 rule 8). The same
checker that passes the committed workflow is run on mutated copies of its `pacs` job,
and each mutation must be reported.
"""

from __future__ import annotations

import copy
import re
import shlex
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
SOUP_LIST = REPO_ROOT / "docs" / "04_soup_list.md"

DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
CONFIG_MOUNT = "docker/orthanc/orthanc.json:/etc/orthanc/orthanc.json"
LOOPBACK_PUBLISH = "127.0.0.1:8042:8042"
PACS_PYTEST = re.compile(r"""\bpytest\b[^\n]*\s-m\s+["']?requires_pacs["']?(\s|$)""")
SHA_PINNED = re.compile(r"^[\w.-]+/[\w.-]+@[0-9a-f]{40}$")


def soup_014_digest() -> str:
    for line in SOUP_LIST.read_text(encoding="utf-8").splitlines():
        if line.startswith("| SOUP-014 |"):
            found = DIGEST.findall(line)
            assert found, "SOUP-014 records no digest"
            return found[0]
    raise AssertionError("SOUP-014 not found in docs/04")


def load_workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _runs(job: dict) -> list[str]:
    return [step["run"] for step in job.get("steps", []) if "run" in step]


def _uses(job: dict) -> list[str]:
    return [step["uses"].split("#")[0].strip() for step in job.get("steps", []) if "uses" in step]


def _docker_runs(job: dict) -> list[list[str]]:
    """Each `docker run` command in the job, tokenised, with line continuations joined."""
    commands = []
    for script in _runs(job):
        joined = script.replace("\\\n", " ")
        for line in joined.splitlines():
            tokens = shlex.split(line, comments=True)
            if tokens[:2] == ["docker", "run"]:
                commands.append(tokens)
    return commands


def _published(tokens: list[str]) -> list[str]:
    out = []
    for i, token in enumerate(tokens):
        if token in ("-p", "--publish") and i + 1 < len(tokens):
            out.append(tokens[i + 1])
        elif token.startswith("--publish="):
            out.append(token.split("=", 1)[1])
    return out


def violations(workflow: dict, digest: str) -> list[str]:
    """Every SRS-094 condition the workflow fails, as a list of short reasons."""
    jobs = workflow.get("jobs", {})
    found: list[str] = []

    quality = jobs.get("quality", {})
    if any(PACS_PYTEST.search(run) for run in _runs(quality)):
        found.append("quality runs requires_pacs")

    job = jobs.get("pacs")
    if job is None:
        return [*found, "no pacs job"]

    docker = _docker_runs(job)
    if len(docker) != 1:
        found.append(f"expected one docker run, found {len(docker)}")
    for tokens in docker:
        images = [t for t in tokens if t.startswith("orthancteam/orthanc")]
        if images != [f"orthancteam/orthanc:24.7.3@{digest}"]:
            found.append(f"image not at the SOUP-014 digest: {images}")
        if not any(CONFIG_MOUNT in t for t in tokens):
            found.append("orthanc.json not mounted")
        if _published(tokens) != [LOOPBACK_PUBLISH]:
            found.append(f"ports published: {_published(tokens)}")
    if "services" in job:
        found.append("service containers are not permitted")

    if not any(PACS_PYTEST.search(run) for run in _runs(job)):
        found.append("pytest -m requires_pacs not run")

    teardown = [
        step
        for step in job.get("steps", [])
        if "always()" in str(step.get("if", "")) and "docker rm -f" in step.get("run", "")
    ]
    if not teardown:
        found.append("no teardown that runs whether or not the tests pass")

    uses = _uses(job)
    if any("upload-artifact" in u for u in uses):
        found.append("uploads an artifact")
    quality_uses = set(_uses(quality))
    for action in uses:
        if not SHA_PINNED.match(action):
            found.append(f"action not pinned by commit SHA: {action}")
        elif action not in quality_uses:
            found.append(f"action not pinned as in quality: {action}")
    return found


def test_TC_135_the_pacs_job_meets_every_condition_of_srs_094():
    found = violations(load_workflow(), soup_014_digest())
    assert not found, f".github/workflows/ci.yml breaks SRS-094 / docs/06 §7.2.1: {found}"


# --- shown able to fail --------------------------------------------------------------


def _step(job: dict, needle: str) -> dict:
    return next(s for s in job["steps"] if needle in s.get("run", ""))


def _wrong_digest(job):
    step = _step(job, "docker run")
    step["run"] = DIGEST.sub("sha256:" + "0" * 64, step["run"])


def _all_interfaces(job):
    step = _step(job, "docker run")
    step["run"] = step["run"].replace(LOOPBACK_PUBLISH, "8042:8042")


def _dimse_port_too(job):
    step = _step(job, "docker run")
    step["run"] = step["run"].replace(
        f"-p {LOOPBACK_PUBLISH}", f"-p {LOOPBACK_PUBLISH} -p 127.0.0.1:4242:4242"
    )


def _upload_step(job):
    job["steps"].append({"uses": "actions/upload-artifact@" + "a" * 40, "with": {"path": "."}})


def _no_teardown(job):
    job["steps"] = [s for s in job["steps"] if "docker rm -f" not in s.get("run", "")]


def _teardown_only_on_success(job):
    _step(job, "docker rm -f").pop("if")


def _marker_missing(job):
    step = _step(job, "pytest")
    step["run"] = "pytest"


def _no_config_mount(job):
    step = _step(job, "docker run")
    step["run"] = step["run"].replace(CONFIG_MOUNT, "/tmp/other.json:/etc/orthanc/x.json")


def _action_by_tag(job):
    job["steps"][0]["uses"] = "actions/checkout@v4"


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (_wrong_digest, "image not at the SOUP-014 digest"),
        (_all_interfaces, "ports published"),
        (_dimse_port_too, "ports published"),
        (_upload_step, "uploads an artifact"),
        (_no_teardown, "no teardown"),
        (_teardown_only_on_success, "no teardown"),
        (_marker_missing, "pytest -m requires_pacs not run"),
        (_no_config_mount, "orthanc.json not mounted"),
        (_action_by_tag, "action not pinned by commit SHA"),
    ],
    ids=lambda v: v.__name__.lstrip("_") if callable(v) else None,
)
def test_TC_135_each_condition_is_reported_when_broken(mutate, expected):
    workflow = copy.deepcopy(load_workflow())
    assert "pacs" in workflow["jobs"], "no pacs job to mutate"
    mutate(workflow["jobs"]["pacs"])
    found = violations(workflow, soup_014_digest())
    assert any(expected in reason for reason in found), f"not reported: {expected!r}; got {found}"


def test_TC_135_a_quality_job_running_requires_pacs_is_reported():
    workflow = copy.deepcopy(load_workflow())
    workflow["jobs"]["quality"]["steps"].append({"run": "pytest -m requires_pacs"})
    assert "quality runs requires_pacs" in violations(workflow, soup_014_digest())


def test_TC_135_a_missing_pacs_job_is_reported():
    workflow = copy.deepcopy(load_workflow())
    workflow["jobs"].pop("pacs", None)
    assert "no pacs job" in violations(workflow, soup_014_digest())
