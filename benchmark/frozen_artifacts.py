"""Fail-closed guards for external packages used by frozen experiments."""

import hashlib
from pathlib import Path
from typing import Iterable


MISSING_ARTIFACT_MESSAGE = (
    "Required frozen artifact missing. Reproduction requires external artifact package."
)


class FrozenArtifactError(RuntimeError):
    """Raised before a frozen output can be regenerated or overwritten."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_frozen_file(path: Path, expected_sha256: str, label: str) -> Path:
    if not path.is_file():
        raise FrozenArtifactError(
            f"{MISSING_ARTIFACT_MESSAGE}\nMissing artifact list:\n- {label}: {path}"
        )
    actual = sha256_file(path)
    if actual != expected_sha256:
        raise FrozenArtifactError(
            f"Frozen artifact hash mismatch: {label}: {path}; "
            f"expected {expected_sha256}, got {actual}. Frozen outputs were not modified."
        )
    return path


def artifact_group_paths(root: Path, pattern: str) -> list[Path]:
    return sorted(root.glob(pattern)) if root.is_dir() else []


def artifact_groups_available(
    groups: Iterable[tuple[str, Path, str, int]],
) -> bool:
    return all(
        len(artifact_group_paths(root, pattern)) == expected
        for _label, root, pattern, expected in groups
    )


def require_artifact_groups(
    groups: Iterable[tuple[str, Path, str, int]],
) -> dict[str, list[Path]]:
    found: dict[str, list[Path]] = {}
    missing = []
    inconsistent = []
    for label, root, pattern, expected in groups:
        paths = artifact_group_paths(root, pattern)
        found[label] = paths
        if len(paths) < expected:
            missing.append(
                f"- {label}: expected {expected}, found {len(paths)}; "
                f"path={root}/{pattern}"
            )
        elif len(paths) > expected:
            inconsistent.append(
                f"- {label}: expected {expected}, found {len(paths)}; "
                f"path={root}/{pattern}"
            )
    if missing:
        raise FrozenArtifactError(
            f"{MISSING_ARTIFACT_MESSAGE}\nMissing artifact list:\n"
            + "\n".join(missing)
        )
    if inconsistent:
        raise FrozenArtifactError(
            "Frozen artifact package count mismatch:\n"
            + "\n".join(inconsistent)
            + "\nFrozen outputs were not modified."
        )
    return found
