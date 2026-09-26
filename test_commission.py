import pytest

from ledgify import compute_commission


def test_base_tier_no_accelerator():
    plan = {"employee_id": "EMP-1", "tiers": [{"threshold": 0, "rate": 0.05}]}
    result = compute_commission(50000, plan)
    assert result == [{"employee_id": "EMP-1", "amount": 2500.0}]


def test_higher_tier_applies_at_threshold():
    plan = {
        "employee_id": "EMP-1",
        "tiers": [{"threshold": 0, "rate": 0.05}, {"threshold": 100000, "rate": 0.08}],
    }
    result = compute_commission(100000, plan)
    assert result == [{"employee_id": "EMP-1", "amount": 8000.0}]


def test_accelerator_applies_above_threshold():
    plan = {
        "employee_id": "EMP-1",
        "tiers": [{"threshold": 0, "rate": 0.05}],
        "accelerator": {"threshold": 200000, "multiplier": 1.5},
    }
    result = compute_commission(250000, plan)
    assert result == [{"employee_id": "EMP-1", "amount": 18750.0}]


def test_accelerator_does_not_apply_below_threshold():
    plan = {
        "employee_id": "EMP-1",
        "tiers": [{"threshold": 0, "rate": 0.05}],
        "accelerator": {"threshold": 200000, "multiplier": 1.5},
    }
    result = compute_commission(100000, plan)
    assert result == [{"employee_id": "EMP-1", "amount": 5000.0}]


def test_splits_divide_commission_correctly():
    plan = {
        "employee_id": "EMP-1",
        "tiers": [{"threshold": 0, "rate": 0.1}],
        "splits": [{"employee_id": "EMP-1", "share": 0.6}, {"employee_id": "EMP-2", "share": 0.4}],
    }
    result = compute_commission(100000, plan)
    assert result == [
        {"employee_id": "EMP-1", "amount": 6000.0},
        {"employee_id": "EMP-2", "amount": 4000.0},
    ]


def test_splits_not_summing_to_one_raises():
    plan = {
        "employee_id": "EMP-1",
        "tiers": [{"threshold": 0, "rate": 0.1}],
        "splits": [{"employee_id": "EMP-1", "share": 0.6}, {"employee_id": "EMP-2", "share": 0.3}],
    }
    with pytest.raises(ValueError):
        compute_commission(100000, plan)


def test_no_tiers_raises():
    plan = {"employee_id": "EMP-1", "tiers": []}
    with pytest.raises(ValueError):
        compute_commission(100000, plan)


def test_deal_amount_below_lowest_threshold_uses_first_tier_rate():
    plan = {
        "employee_id": "EMP-1",
        "tiers": [{"threshold": 1000, "rate": 0.05}, {"threshold": 50000, "rate": 0.08}],
    }
    result = compute_commission(500, plan)
    assert result == [{"employee_id": "EMP-1", "amount": 25.0}]
