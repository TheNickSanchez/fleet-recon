"""Builds the ``chat.csv_preview`` payload (SAD §2.6, PRD FR-10, SFS §5).

One renderer for every asset_ops run, 4 names or 50. The model never sees the
CSV body -- only the host reads the report file to build this payload.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

# Fixed asset-ops step 1+2 column set (SAD §2.6 / SFS §5). Any column missing
# from the actual report (e.g. the MDM step failed) is padded with "" rather
# than reshaping the contract per-run.
CSV_PREVIEW_HEADERS: tuple[str, ...] = (
    "Username",
    "Serial",
    "Platform",
    "State",
    "Substate",
    "Model",
    "Asset Tag",
    "Notes",
    "MDM",
    "MDM Status",
    "MDM Last Check-In",
    "MDM Detail",
)

PREVIEW_ROW_CAP = 10


@dataclass(frozen=True)
class CsvPreview:
    type: str
    filename: str
    headers: tuple[str, ...]
    preview_rows: tuple[dict[str, str], ...]
    row_count: int
    truncated: bool
    file_ref: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "filename": self.filename,
            "headers": list(self.headers),
            "preview_rows": [dict(row) for row in self.preview_rows],
            "row_count": self.row_count,
            "truncated": self.truncated,
            "file_ref": self.file_ref,
        }


def build_csv_preview(report_path: Path, filename: str, file_ref: str) -> CsvPreview:
    """Read the asset-ops report file and cap the preview at 10 data rows.

    Missing fixed-schema columns (e.g. the run only completed step 1) are
    reindexed to "" so the payload shape never varies by run outcome.
    """
    df = pd.read_csv(report_path, dtype=str).fillna("")
    df = df.reindex(columns=list(CSV_PREVIEW_HEADERS), fill_value="")
    row_count = len(df)
    preview = df.head(PREVIEW_ROW_CAP)
    preview_rows = tuple(
        {header: str(row[header]) for header in CSV_PREVIEW_HEADERS}
        for _, row in preview.iterrows()
    )
    return CsvPreview(
        type="chat.csv_preview",
        filename=filename,
        headers=CSV_PREVIEW_HEADERS,
        preview_rows=preview_rows,
        row_count=row_count,
        truncated=row_count > PREVIEW_ROW_CAP,
        file_ref=file_ref,
    )
