from connectors import validate_quote_fields


def valid_opportunity():
    return {
        "sku": "SASE-2200",
        "subscription_start": "2026-10-01",
        "subscription_end": "2027-10-01",
    }


def test_valid_opportunity_has_no_errors():
    assert validate_quote_fields(valid_opportunity()) == []


def test_malformed_sku_is_flagged():
    opp = valid_opportunity()
    opp["sku"] = "not-a-valid-sku"
    errors = validate_quote_fields(opp)
    assert any("sku" in e for e in errors)


def test_end_before_start_is_flagged():
    opp = valid_opportunity()
    opp["subscription_end"] = "2026-01-01"
    errors = validate_quote_fields(opp)
    assert any("subscription_start is not before subscription_end" in e for e in errors)


def test_missing_fields_are_flagged():
    errors = validate_quote_fields({})
    assert len(errors) >= 3


def test_blank_dates_from_live_system_are_reported_not_crashed():
    # A blank Date field in Salesforce comes back as None, not "".
    opp = valid_opportunity()
    opp["subscription_start"] = None
    opp["subscription_end"] = None
    errors = validate_quote_fields(opp)
    assert "subscription_start is missing" in errors
    assert "subscription_end is missing" in errors


def test_date_order_not_checked_when_a_date_is_malformed():
    opp = valid_opportunity()
    opp["subscription_end"] = "next year"
    errors = validate_quote_fields(opp)
    assert any("subscription_end 'next year'" in e for e in errors)
    assert not any("is not before" in e for e in errors)
