from core import BaseAgent


def compute_commission(deal_amount, commission_plan):
    tiers = sorted(commission_plan["tiers"], key=lambda t: t["threshold"])
    if not tiers:
        raise ValueError("commission_plan has no tiers defined")

    rate = tiers[0]["rate"]
    for tier in tiers:
        if deal_amount >= tier["threshold"]:
            rate = tier["rate"]
    base_commission = deal_amount * rate

    accelerator = commission_plan.get("accelerator")
    if accelerator and deal_amount >= accelerator["threshold"]:
        base_commission *= accelerator["multiplier"]

    splits = commission_plan.get("splits") or [{"employee_id": commission_plan["employee_id"], "share": 1.0}]
    total_share = sum(split["share"] for split in splits)
    if abs(total_share - 1.0) > 0.001:
        raise ValueError(f"commission_plan splits sum to {total_share}, expected 1.0")

    line_items = [
        {"employee_id": split["employee_id"], "amount": round(base_commission * split["share"], 2)}
        for split in splits
    ]
    return line_items


class LedgifyAgent(BaseAgent):
    name = "ledgify"

    def __init__(self, audit_log, approval_queue, escalation_queue, salesforce, netsuite, workday):
        super().__init__(audit_log, approval_queue, escalation_queue)
        self.salesforce = salesforce
        self.netsuite = netsuite
        self.workday = workday

    def handle_ar_status_change(self, invoice_id, opportunity_id, deal_amount):
        status = self.netsuite.get_ar_status(invoice_id)
        if status != "Paid":
            self.log("ar_not_cleared", {"invoice_id": invoice_id, "status": status})
            return {"status": "waiting", "ar_status": status}

        commission_plan = self.salesforce.get_commission_plan(opportunity_id)
        if commission_plan is None:
            self.log("commission_plan_not_found", {"opportunity_id": opportunity_id})
            return {"status": "error", "reason": "commission_plan_not_found"}

        try:
            line_items = compute_commission(deal_amount, commission_plan)
        except ValueError as error:
            self.log("commission_computation_failed", {"opportunity_id": opportunity_id, "error": str(error)})
            return {"status": "error", "reason": "commission_computation_failed", "detail": str(error)}

        staged_ids = []
        for line_item in line_items:
            approval_id = self.stage_for_approval(
                kind="commission_line",
                payload={"invoice_id": invoice_id, "opportunity_id": opportunity_id, **line_item},
                approver_role="finance_hr_approver",
                dedup_key=f"{invoice_id}:{line_item['employee_id']}",
            )
            staged_ids.append(approval_id)

        return {"status": "staged", "line_items": line_items, "approval_ids": staged_ids}

    def post_approved_line(self, approval_item_id, approved_by):
        approved = self.approval_queue.approve(approval_item_id, approved_by, expected_kind="commission_line")
        payload = approved["payload"]
        staged = self.workday.stage_compensation_line(
            payload["employee_id"], {"amount": payload["amount"], "source_invoice": payload["invoice_id"]}
        )
        self.log("commission_posted_to_workday_staging", staged)
        return staged
