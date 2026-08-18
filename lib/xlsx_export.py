"""Validated, atomic XLSX export for canonical tabular artifacts."""

from __future__ import annotations

import os
import tempfile
import zipfile
from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal


def validate_xlsx_against_csv(xlsx_path: Path, csv_path: Path) -> None:
    """Fail unless a closed XLSX is intact and semantically matches its CSV."""
    try:
        with zipfile.ZipFile(xlsx_path) as workbook_zip:
            bad_member = workbook_zip.testzip()
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"XLSX is not a valid readable ZIP archive: {xlsx_path}") from exc
    if bad_member is not None:
        raise ValueError(f"XLSX contains a corrupt ZIP member: {bad_member}")

    csv_frame = pd.read_csv(csv_path)
    xlsx_frame = pd.read_excel(xlsx_path)
    if list(xlsx_frame.columns) != list(csv_frame.columns):
        raise ValueError("XLSX schema does not match the canonical CSV")
    if len(xlsx_frame) != len(csv_frame):
        raise ValueError("XLSX row count does not match the canonical CSV")

    key_columns = ["season", "player_id"]
    missing_keys = [column for column in key_columns if column not in csv_frame.columns]
    if missing_keys:
        raise ValueError(f"canonical CSV is missing player-season keys: {missing_keys}")
    try:
        assert_frame_equal(
            xlsx_frame[key_columns], csv_frame[key_columns],
            check_dtype=False, check_exact=True,
        )
    except AssertionError as exc:
        raise ValueError("XLSX player-season keys do not match the canonical CSV") from exc
    try:
        assert_frame_equal(
            xlsx_frame, csv_frame, check_dtype=False, check_exact=False,
            rtol=1e-12, atol=1e-12,
        )
    except AssertionError as exc:
        raise ValueError("XLSX contents do not semantically match the canonical CSV") from exc


def write_validated_xlsx(master_frame: pd.DataFrame, csv_path: Path, xlsx_path: Path) -> None:
    """Atomically replace an XLSX only after complete write and validation."""
    xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{xlsx_path.stem}.", suffix=".tmp.xlsx", dir=xlsx_path.parent,
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        master_frame.to_excel(temporary_path, index=False)
        validate_xlsx_against_csv(temporary_path, csv_path)
        os.replace(temporary_path, xlsx_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
