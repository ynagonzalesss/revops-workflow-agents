from core import BaseAgent
from connectors import ConnectorError, validate_quote_fields


class GatekeeperAgent(BaseAgent):
    name = "gatekeeper"

    def __init__(self, audit_log, approval_queue, escalation_queue, salesforce, netsuite, workday,
                 capacity_owner="delivery_ops_lead", capacity_sla_hours=4):
        super().__init__(audit_log, approval_queue, escalation_queue)
        self.salesforce = salesforce
        self.netsuite = netsuite
        self.workday = workday
        self.capacity_owner = capacity_owner
        self.capacity_sla_hours = capacity_sla_hours

    def handle_closed_won(self, opportunity_id):
        try:
            opportunity = self.salesforce.get_closed_won_opportunity(opportunity_id)
        except ConnectorError as error:
            self.log("source_system_error", {"opportunity_id": opportunity_id, "error": str(error)})
            return {"status": "error", "reason": "source_system_error", "detail": str(error)}
        if opportunity is None:
            self.log("opportunity_not_found", {"opportunity_id": opportunity_id})
            return {"status": "error", "reason": "opportunity_not_found"}

        errors = validate_quote_fields(opportunity)
        if errors:
            self.log("validation_failed", {"opportunity_id": opportunity_id, "errors": errors})
            return {"status": "blocked", "reason": "validation_failed", "errors": errors}

        capacity = self.workday.get_delivery_capacity(opportunity["tam_id"])
        if not capacity["available"]:
            escalation_id = self.escalate(
                reason="insufficient_delivery_capacity",
                owner=self.capacity_owner,
                sla_hours=self.capacity_sla_hours,
                payload={"opportunity_id": opportunity_id, "tam_id": opportunity["tam_id"], "capacity": capacity},
                dedup_key=opportunity_id,
            )
            return {"status": "gated", "reason": "insufficient_capacity", "escalation_id": escalation_id}

        schedule = {
            "opportunity_id": opportunity_id,
            "term_months": opportunity.get("term_months"),
            "start": opportunity.get("subscription_start"),
            "end": opportunity.get("subscription_end"),
            "products": opportunity.get("line_items", []),
        }
        self.netsuite.draft_billing_schedule(opportunity_id, schedule)
        approval_id = self.stage_for_approval(
            "billing_schedule", schedule, approver_role="deal_desk", dedup_key=opportunity_id
        )

        return {"status": "staged", "approval_id": approval_id}

    def unfreeze_provisioning(self, opportunity_id, approval_item_id, approved_by):
        approved = self.approval_queue.approve(
            approval_item_id, approved_by,
            expected_kind="billing_schedule",
            expected_payload={"opportunity_id": opportunity_id},
        )
        self.log("provisioning_unfrozen", {"opportunity_id": opportunity_id, "approval": approved})
        return {"status": "provisioning_unfrozen", "opportunity_id": opportunity_id}
