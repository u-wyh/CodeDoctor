"""Download the official Codeflaws archive and classification metadata."""

import argparse
import hashlib
import json
import shutil
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.config import (  # noqa: E402
    CODEFLAWS_ARCHIVE,
    CODEFLAWS_ARCHIVE_URL,
    CODEFLAWS_CLASSIFICATION,
    CODEFLAWS_DEFECT_TABLE_URL,
    CODEFLAWS_DOWNLOAD_RECORD,
    CODEFLAWS_METADATA_ROOT,
    CODEFLAWS_RAW_ROOT,
)


class DefectTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_row = False
        self.in_cell = False
        self.cell_parts: list[str] = []
        self.row: list[str] = []
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "tr":
            self.in_row = True
            self.row = []
        elif self.in_row and tag.lower() in {"td", "th"}:
            self.in_cell = True
            self.cell_parts = []

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in {"td", "th"} and self.in_cell:
            self.row.append(" ".join("".join(self.cell_parts).split()))
            self.in_cell = False
        elif lowered == "tr" and self.in_row:
            if self.row:
                self.rows.append(self.row)
            self.in_row = False


def _download(url: str, destination: Path) -> dict[str, object]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    if destination.exists():
        print(f"Archive already exists, skipping download: {destination}")
        return _file_record(destination, url, resumed=False, reused=True)

    offset = partial.stat().st_size if partial.exists() else 0
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "CodeDoctor-Codeflaws-Downloader/1.0"},
    )
    if offset:
        request.add_header("Range", f"bytes={offset}-")

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            resumed = offset > 0 and response.status == 206
            mode = "ab" if resumed else "wb"
            if offset and not resumed:
                print("Server did not honor Range; restarting partial download")
            with partial.open(mode) as output:
                shutil.copyfileobj(response, output, length=1024 * 1024)
    except (OSError, urllib.error.URLError) as exc:
        raise RuntimeError(f"failed to download {url}: {exc}") from exc

    partial.replace(destination)
    return _file_record(destination, url, resumed=resumed, reused=False)


def _file_record(
    path: Path, url: str, *, resumed: bool, reused: bool
) -> dict[str, object]:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "source_url": url,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "archive_path": path.name,
        "size_bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
        "resumed": resumed,
        "reused_existing_archive": reused,
    }


def _extract_archive(archive: Path, raw_root: Path) -> bool:
    marker = raw_root / ".extracted.json"
    if marker.exists():
        print(f"Extraction marker exists, skipping extraction: {marker}")
        return False

    existing = [path for path in raw_root.iterdir() if path.name != ".gitkeep"]
    if existing:
        names = ", ".join(path.name for path in existing[:5])
        raise RuntimeError(
            f"raw directory is not empty and has no extraction marker: {names}"
        )

    raw_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="codeflaws-extract-", dir=raw_root.parent
    ) as temporary:
        staging = Path(temporary)
        with tarfile.open(archive, mode="r:gz") as bundle:
            bundle.extractall(staging, filter="data")
        for item in staging.iterdir():
            destination = raw_root / item.name
            if destination.exists():
                raise RuntimeError(f"refusing to overwrite extracted path: {destination}")
            shutil.move(str(item), destination)

    marker.write_text(
        json.dumps(
            {
                "archive": archive.name,
                "extracted_at": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return True


def _download_classification() -> dict[str, object]:
    request = urllib.request.Request(
        CODEFLAWS_DEFECT_TABLE_URL,
        headers={"User-Agent": "CodeDoctor-Codeflaws-Downloader/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            content = response.read()
    except (OSError, urllib.error.URLError) as exc:
        raise RuntimeError(
            f"failed to download classification table: {exc}"
        ) from exc

    parser = DefectTableParser()
    parser.feed(content.decode("utf-8", errors="replace"))
    classifications: dict[str, dict[str, str]] = {}
    for row in parser.rows:
        if len(row) < 4 or "-bug-" not in row[0]:
            continue
        classifications[row[0]] = {
            "defect_class": row[1],
            "error_type": row[2],
            "error_code": row[3],
        }

    CODEFLAWS_CLASSIFICATION.write_text(
        json.dumps(
            {
                "source_url": CODEFLAWS_DEFECT_TABLE_URL,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "sha256": hashlib.sha256(content).hexdigest(),
                "case_count": len(classifications),
                "cases": classifications,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "source_url": CODEFLAWS_DEFECT_TABLE_URL,
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "case_count": len(classifications),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-extract",
        action="store_true",
        help="download and verify the archive without extracting it",
    )
    args = parser.parse_args()

    for directory in (
        CODEFLAWS_ARCHIVE.parent,
        CODEFLAWS_RAW_ROOT,
        CODEFLAWS_METADATA_ROOT,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    try:
        archive_record = _download(CODEFLAWS_ARCHIVE_URL, CODEFLAWS_ARCHIVE)
        classification_record = _download_classification()
        extracted = False
        if not args.no_extract:
            extracted = _extract_archive(CODEFLAWS_ARCHIVE, CODEFLAWS_RAW_ROOT)
        record = {
            "dataset": "codeflaws",
            "archive": archive_record,
            "classification": classification_record,
            "extracted_this_run": extracted,
        }
        CODEFLAWS_DOWNLOAD_RECORD.write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(record, indent=2, sort_keys=True))
        return 0
    except RuntimeError as exc:
        print(f"download_codeflaws: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
