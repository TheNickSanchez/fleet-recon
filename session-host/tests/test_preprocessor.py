from __future__ import annotations

from fleet_session_host.preprocessor import bind_skill, extract_identities, is_vuln_phrasing


def test_example_request_binds_asset_ops_with_four_names():
    text = "look up these users devices\nnina.patel\nchris.okonkwo\nsam.lee\njordan.nguyen"
    result = bind_skill(text, has_csv=False)

    assert result.mode == "asset_ops"
    assert result.input_count == 4
    assert set(result.identities) == {"nina.patel", "chris.okonkwo", "sam.lee", "jordan.nguyen"}
    assert not result.rejected


def test_instruction_stopwords_are_not_identities():
    identities = extract_identities("look up these users devices")
    assert identities == []


def test_one_serial_binds_device_lookup():
    result = bind_skill("look up serial C02FL1234ABC", has_csv=False)
    assert result.mode == "device_lookup"
    assert result.input_count == 1
    assert result.identities == ("c02fl1234abc",)


def test_one_username_no_list_binds_device_lookup():
    result = bind_skill("look up the device for jdoe", has_csv=False)
    assert result.mode == "device_lookup"
    assert result.input_count == 1
    assert result.identities == ("jdoe",)


def test_any_csv_binds_asset_ops_even_with_no_pasted_text():
    result = bind_skill("", has_csv=True)
    assert result.mode == "asset_ops"


def test_csv_wins_over_accompanying_text_routing():
    # A single name pasted alongside a CSV upload must not force device_lookup;
    # CSV always binds asset_ops (PRD FR-2 / SFS §4.2).
    result = bind_skill("jdoe", has_csv=True)
    assert result.mode == "asset_ops"


def test_zero_identities_is_rejected_without_connector_calls():
    result = bind_skill("look up these users devices", has_csv=False)
    assert result.rejected is True
    assert result.mode is None
    assert result.rejection_reason


def test_emails_dedupe_with_bare_usernames():
    identities = extract_identities("nina.patel@example.com nina.patel")
    assert identities == ["nina.patel"]


def test_fifty_names_use_the_same_asset_ops_route_as_four():
    names = "\n".join(f"user{n}" for n in range(50))
    result = bind_skill(f"look up these users devices\n{names}", has_csv=False)
    assert result.mode == "asset_ops"
    assert result.input_count == 50


def test_vuln_phrasing_detection():
    assert is_vuln_phrasing("any vulnerabilities on this host?")
    assert is_vuln_phrasing("check CVE exposure")
    assert not is_vuln_phrasing("look up jdoe")
