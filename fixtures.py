def build_mock_session():
    return {
        "opportunities": {
            "OPP-1001": {
                "id": "OPP-1001",
                "tam_id": "TAM-42",
                "sku": "SASE-2200",
                "subscription_start": "2026-10-01",
                "subscription_end": "2027-10-01",
                "term_months": 12,
                "line_items": ["SASE-2200", "ZTNA-1100"],
                "required_skills": ["SASE_CERT"],
            },
            "OPP-1002": {
                "id": "OPP-1002",
                "tam_id": "TAM-42",
                "sku": "bad-sku",
                "subscription_start": "2026-11-01",
                "subscription_end": "2026-10-01",
                "term_months": 12,
                "line_items": ["SASE-2200"],
                "required_skills": [],
            },
            "OPP-1003": {
                "id": "OPP-1003",
                "tam_id": "TAM-07",
                "sku": "SASE-2200",
                "subscription_start": "2026-10-01",
                "subscription_end": "2027-10-01",
                "term_months": 12,
                "line_items": ["SASE-2200"],
                "required_skills": [],
            },
        },
        "commission_plans": {
            "OPP-1001": {
                "employee_id": "EMP-9",
                "tiers": [{"threshold": 0, "rate": 0.05}, {"threshold": 100000, "rate": 0.08}],
                "accelerator": {"threshold": 250000, "multiplier": 1.2},
                "splits": [{"employee_id": "EMP-9", "share": 0.7}, {"employee_id": "EMP-11", "share": 0.3}],
            }
        },
        "invoices": {"INV-500": {"status": "Paid"}, "INV-501": {"status": "Sent"}},
        "capacity": {"TAM-42": {"available": True, "slots": 2}, "TAM-07": {"available": False, "slots": 0}},
        "certifications": {},
    }
