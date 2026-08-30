from __future__ import annotations

from pathlib import Path

from fleet_session_host.csv_preview import CSV_PREVIEW_HEADERS, build_csv_preview


def test_schema_and_row_cap(tmp_path: Path):
    header = "Username,Serial,Platform,State,Substate,Model,Asset Tag,Notes,MDM,MDM Status,MDM Last Check-In,MDM Detail"
    rows = [f"user{i},SN{i},macOS,In use,Primary,MacBook,AT{i},,Jamf,Managed,2026-08-20," for i in range(15)]
    report = tmp_path / "devices-abc.csv"
    report.write_text(header + "\n" + "\n".join(rows) + "\n")

    preview = build_csv_preview(report, filename="devices-abc.csv", file_ref="devices-abc.csv")
    payload = preview.to_dict()

    assert payload["type"] == "chat.csv_preview"
    assert payload["headers"] == list(CSV_PREVIEW_HEADERS)
    assert payload["row_count"] == 15
    assert len(payload["preview_rows"]) == 10
    assert payload["truncated"] is True
    assert payload["file_ref"] == "devices-abc.csv"
    assert payload["filename"] == "devices-abc.csv"
    # Every preview row is a flat mapping over the fixed header set only.
    for row in payload["preview_rows"]:
        assert set(row.keys()) == set(CSV_PREVIEW_HEADERS)


def test_missing_mdm_columns_are_padded_blank(tmp_path: Path):
    # Only step 1 ran: base columns only, no MDM enrichment yet.
    report = tmp_path / "devices-step1-only.csv"
    report.write_text(
        "Username,Serial,Platform,State,Substate,Model,Asset Tag,Notes\n"
        "nina.patel,ABC123,macOS,In use,Primary,MacBook,AT1,\n"
    )

    preview = build_csv_preview(report, filename="devices-x.csv", file_ref="devices-x.csv")
    payload = preview.to_dict()

    assert payload["row_count"] == 1
    assert payload["truncated"] is False
    row = payload["preview_rows"][0]
    assert row["Username"] == "nina.patel"
    assert row["MDM"] == ""
    assert row["MDM Status"] == ""
    assert row["MDM Last Check-In"] == ""
    assert row["MDM Detail"] == ""


def test_exactly_ten_rows_is_not_truncated(tmp_path: Path):
    header = "Username,Serial,Platform,State,Substate,Model,Asset Tag,Notes,MDM,MDM Status,MDM Last Check-In,MDM Detail"
    rows = [f"user{i},SN{i},macOS,In use,Primary,MacBook,AT{i},,Jamf,Managed,2026-08-20," for i in range(10)]
    report = tmp_path / "devices-ten.csv"
    report.write_text(header + "\n" + "\n".join(rows) + "\n")

    payload = build_csv_preview(report, filename="devices-ten.csv", file_ref="devices-ten.csv").to_dict()
    assert payload["row_count"] == 10
    assert payload["truncated"] is False
    assert len(payload["preview_rows"]) == 10
