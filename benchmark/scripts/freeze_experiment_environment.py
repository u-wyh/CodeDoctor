"""Freeze Pilot identity, toolchain, Docker image, and Git state."""

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.config import (  # noqa: E402
    CODEFLAWS_DOWNLOAD_RECORD,
    CODEFLAWS_MANIFEST,
    CODEFLAWS_PILOT,
    EXPERIMENT_ENVIRONMENT,
    MANIFEST_SCHEMA_VERSION,
    PILOT_RANDOM_SEED,
    PROJECT_ROOT,
)
from benchmark.models import load_manifest  # noqa: E402
from sandbox.runner.config import RunnerConfig  # noqa: E402
from fault_localization.collector import (  # noqa: E402
    COVERAGE_COMPILER_COMMAND,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _command(command: list[str], *, check: bool = True) -> str:
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return result.stdout.strip()


def main() -> int:
    config = RunnerConfig()
    try:
        image = json.loads(
            _command([config.docker_command, "image", "inspect", config.docker_image])
        )[0]
        gcc = _command(
            [config.docker_command, "run", "--rm", "--network", "none", config.docker_image, "gcc", "--version"]
        ).splitlines()[0]
        gcov = _command(
            [config.docker_command, "run", "--rm", "--network", "none", config.docker_image, "gcov", "--version"]
        ).splitlines()[0]
    except (RuntimeError, json.JSONDecodeError, IndexError) as exc:
        print(f"freeze_experiment_environment: {exc}", file=sys.stderr)
        return 1

    git_commit = (
        _command(["git", "rev-parse", "--verify", "HEAD"], check=False)
        or None
    )
    repository_state = "committed" if git_commit else "unborn_repository"
    download = json.loads(CODEFLAWS_DOWNLOAD_RECORD.read_text(encoding="utf-8"))
    pilot_cases = list(load_manifest(CODEFLAWS_PILOT))
    document = {
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "dataset": "codeflaws",
        "archive_sha256": download["archive"]["sha256"],
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "manifest_sha256": _sha256(CODEFLAWS_MANIFEST),
        "pilot_sha256": _sha256(CODEFLAWS_PILOT),
        "pilot_random_seed": PILOT_RANDOM_SEED,
        "pilot_case_ids": [case.case_id for case in pilot_cases],
        "pilot_case_count": len(pilot_cases),
        "gcc_version": gcc,
        "gcov_version": gcov,
        "coverage_compiler_command": COVERAGE_COMPILER_COMMAND,
        "coverage_run_timeout_seconds": config.run_timeout_seconds,
        "coverage_counter_isolation": "fresh_workspace_per_repair_test",
        "coverage_fatal_signal_dump": True,
        "docker_image": config.docker_image,
        "docker_image_id": image["Id"],
        "docker_repo_digests": image.get("RepoDigests", []),
        "docker_created": image.get("Created"),
        "dockerfile_sha256": _sha256(PROJECT_ROOT / "sandbox/docker/Dockerfile"),
        "git_commit": git_commit,
        "git_repository_state": repository_state,
        "git_remote_configured": bool(_command(["git", "remote"], check=False)),
    }
    EXPERIMENT_ENVIRONMENT.parent.mkdir(parents=True, exist_ok=True)
    temporary = EXPERIMENT_ENVIRONMENT.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(EXPERIMENT_ENVIRONMENT)
    print(json.dumps(document, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
