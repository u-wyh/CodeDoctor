"""Run reference filtering and V3/V4 validation with local checkpoints."""

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.config import (  # noqa: E402
    CODEFLAWS_REPAIR_PILOT,
    PHASE8_EVALUATION_SET,
    PHASE9_ARTIFACT_ROOT,
    PHASE9_DIFFERENTIAL_MANIFEST,
    PHASE9_PATCH_CORPUS,
    PHASE9_RANDOM_SEED,
)
from benchmark.models import load_manifest  # noqa: E402
from validation_phase9.batch import DockerBatchExecutor  # noqa: E402
from validation_phase9.corpus import load_patch_source  # noqa: E402
from validation_phase9.pipeline import (  # noqa: E402
    differential_manifest,
    run_reference_case,
    validate_patch,
)


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("references", "patches", "all"), default="all")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    corpus = _load(PHASE9_PATCH_CORPUS)
    cases = {
        case.case_id: case
        for path in (CODEFLAWS_REPAIR_PILOT, PHASE8_EVALUATION_SET)
        for case in load_manifest(path)
    }
    corpus_case_ids = sorted({item["case_id"] for item in corpus["entries"]})
    executor = DockerBatchExecutor()
    reference_root = PHASE9_ARTIFACT_ROOT / "reference"
    patch_root = PHASE9_ARTIFACT_ROOT / "patch"

    if args.stage in {"references", "all"}:
        for index, case_id in enumerate(corpus_case_ids, start=1):
            path = reference_root / f"{case_id}.json"
            if args.resume and path.is_file():
                print(f"[reference {index}/{len(corpus_case_ids)}] {case_id}: resumed", flush=True)
                continue
            value = run_reference_case(
                cases[case_id], executor, seed=PHASE9_RANDOM_SEED
            )
            _write(path, value)
            print(
                f"[reference {index}/{len(corpus_case_ids)}] {case_id}: "
                f"proposed={value['proposal_count']} accepted={value['accepted_count']} "
                f"sanitizer_eligible={len(value['sanitizer_eligible_official_test_ids'])}",
                flush=True,
            )
        references = [_load(reference_root / f"{case_id}.json") for case_id in corpus_case_ids]
        manifest = differential_manifest(references)
        _write(PHASE9_DIFFERENTIAL_MANIFEST, manifest)
        print(
            f"differential manifest: proposed={manifest['proposal_count']} "
            f"accepted={manifest['accepted_test_count']} "
            f"hash={manifest['overall_manifest_hash']}",
            flush=True,
        )

    if args.stage in {"patches", "all"}:
        missing = [case_id for case_id in corpus_case_ids if not (reference_root / f"{case_id}.json").is_file()]
        if missing:
            raise FileNotFoundError(f"reference checkpoints missing: {missing[:3]}")
        entries = list(corpus["entries"])
        for index, entry in enumerate(entries, start=1):
            path = patch_root / (entry["patch_id"].replace("/", "__") + ".json")
            if args.resume and path.is_file():
                print(f"[patch {index}/{len(entries)}] {entry['patch_id']}: resumed", flush=True)
                continue
            reference = _load(reference_root / f"{entry['case_id']}.json")
            value = validate_patch(
                entry=entry,
                source=load_patch_source(entry),
                case=cases[entry["case_id"]],
                reference_record=reference,
                executor=executor,
            )
            _write(path, value)
            print(
                f"[patch {index}/{len(entries)}] {entry['patch_id']}: "
                f"V3={value['V3']} V4={value['V4']} strong={value['strongly_validated']}",
                flush=True,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
