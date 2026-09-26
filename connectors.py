import re


class ConnectorError(Exception):
    """Base error for any connector (mock or live) failing to reach or read a source system."""


class SalesforceConnector:
    def __init__(self, session=None):
        self.session = session or {}

    def get_closed_won_opportunity(self, opportunity_id):
        return self.session.get("opportunities", {}).get(opportunity_id)

    def get_opportunities_requiring_skill(self, skill):
        opps = self.session.get("opportunities", {}).values()
        return [o for o in opps if skill in o.get("required_skills", [])]

    def tag_qualified_rep(self, opportunity_id, employee_id):
        opp = self.session["opportunities"][opportunity_id]
        tagged = opp.setdefault("tagged_experts", [])
        if employee_id not in tagged:
            tagged.append(employee_id)
        return opp

    def get_commission_plan(self, opportunity_id):
        return self.session.get("commission_plans", {}).get(opportunity_id)


class NetSuiteConnector:
    def __init__(self, session=None):
        self.session = session or {}

    def draft_billing_schedule(self, opportunity_id, schedule):
        drafts = self.session.setdefault("billing_schedule_drafts", {})
        drafts[opportunity_id] = schedule
        return schedule

    def get_ar_status(self, invoice_id):
        return self.session.get("invoices", {}).get(invoice_id, {}).get("status")

    def set_openair_billable_rate(self, employee_id, new_rate, reason):
        rates = self.session.setdefault("openair_rates", {})
        previous = rates.get(employee_id)
        rates[employee_id] = new_rate
        return {"employee_id": employee_id, "previous_rate": previous, "new_rate": new_rate, "reason": reason}


class WorkdayConnector:
    def __init__(self, session=None):
        self.session = session or {}

    def get_delivery_capacity(self, team_or_tam_id):
        return self.session.get("capacity", {}).get(team_or_tam_id, {"available": False, "slots": 0})

    def get_certifications(self, employee_id):
        return self.session.get("certifications", {}).get(employee_id, [])

    def stage_compensation_line(self, employee_id, line_item):
        staged = self.session.setdefault("staged_compensation", [])
        staged.append({"employee_id": employee_id, **line_item})
        return staged[-1]


QUOTE_FIELD_RULES = {
    "sku": re.compile(r"^[A-Z]{2,5}-\d{3,6}$"),
    "subscription_start": re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    "subscription_end": re.compile(r"^\d{4}-\d{2}-\d{2}$"),
}


def validate_quote_fields(opportunity):
    errors = []
    well_formed = set()
    for field_name, pattern in QUOTE_FIELD_RULES.items():
        value = opportunity.get(field_name)
        if value is None or value == "":
            errors.append(f"{field_name} is missing")
        elif not pattern.match(str(value)):
            errors.append(f"{field_name} '{value}' does not match expected format")
        else:
            well_formed.add(field_name)
    # Only compare dates when both are present and well-formed; a blank field from a live
    # system comes back as None, and comparing None to None would crash instead of reporting.
    if {"subscription_start", "subscription_end"} <= well_formed:
        if opportunity["subscription_start"] >= opportunity["subscription_end"]:
            errors.append("subscription_start is not before subscription_end")
    return errors
