from core import BaseAgent


class SynaptoAgent(BaseAgent):
    name = "synapto"

    def __init__(self, audit_log, approval_queue, escalation_queue, salesforce, netsuite, workday,
                 skill_gap_threshold=3):
        super().__init__(audit_log, approval_queue, escalation_queue)
        self.salesforce = salesforce
        self.netsuite = netsuite
        self.workday = workday
        self.skill_gap_threshold = skill_gap_threshold

    def handle_certification_update(self, employee_id, certification, new_billable_rate):
        matching_opportunities = self.salesforce.get_opportunities_requiring_skill(certification)
        for opportunity in matching_opportunities:
            self.salesforce.tag_qualified_rep(opportunity["id"], employee_id)
            self.log("tagged_qualified_rep", {"opportunity_id": opportunity["id"], "employee_id": employee_id,
                                               "certification": certification})

        rate_change = self.netsuite.set_openair_billable_rate(
            employee_id, new_billable_rate, reason=f"certification_gained:{certification}"
        )
        self.log("billable_rate_updated", rate_change)

        return {
            "status": "processed",
            "tagged_opportunities": [o["id"] for o in matching_opportunities],
            "rate_change": rate_change,
        }

    def check_skill_gap(self, category, pipeline_count, certified_headcount):
        gap = pipeline_count - certified_headcount
        if gap >= self.skill_gap_threshold:
            escalation_id = self.escalate(
                reason="skill_gap_exceeds_threshold",
                owner="capability_planning_lead",
                sla_hours=48,
                payload={"category": category, "pipeline_count": pipeline_count,
                         "certified_headcount": certified_headcount, "gap": gap},
            )
            return {"status": "alerted", "gap": gap, "escalation_id": escalation_id}
        return {"status": "ok", "gap": gap}
