from core import AuditLog, ApprovalQueue, EscalationQueue
from connectors import SalesforceConnector, NetSuiteConnector, WorkdayConnector
from fixtures import build_mock_session
from ledgify import LedgifyAgent


def build_ledgify():
    session = build_mock_session()
    agent = LedgifyAgent(
        AuditLog(), ApprovalQueue(), EscalationQueue(),
        SalesforceConnector(session), NetSuiteConnector(session), WorkdayConnector(session),
    )
    return agent, session


def test_unpaid_invoice_does_not_stage_anything():
    agent, _ = build_ledgify()
    result = agent.handle_ar_status_change("INV-501", "OPP-1001", deal_amount=300000)
    assert result["status"] == "waiting"
    assert len(agent.approval_queue.pending) == 0


def test_paid_invoice_stages_split_commission_but_does_not_post():
    agent, _ = build_ledgify()
    result = agent.handle_ar_status_change("INV-500", "OPP-1001", deal_amount=300000)
    assert result["status"] == "staged"
    assert len(result["line_items"]) == 2
    assert len(agent.approval_queue.pending) == 2
    assert len(agent.workday.session.get("staged_compensation", [])) == 0


def test_posting_only_happens_after_explicit_approval():
    agent, _ = build_ledgify()
    result = agent.handle_ar_status_change("INV-500", "OPP-1001", deal_amount=300000)
    approval_id = result["approval_ids"][0]
    agent.post_approved_line(approval_id, approved_by="finance_manager")
    assert len(agent.workday.session["staged_compensation"]) == 1
    assert approval_id not in agent.approval_queue.pending


def test_repeated_ar_event_does_not_double_stage():
    agent, _ = build_ledgify()
    first = agent.handle_ar_status_change("INV-500", "OPP-1001", deal_amount=300000)
    second = agent.handle_ar_status_change("INV-500", "OPP-1001", deal_amount=300000)
    assert sorted(first["approval_ids"]) == sorted(second["approval_ids"])
    assert len(agent.approval_queue.pending) == 2


def test_missing_commission_plan_returns_error():
    agent, _ = build_ledgify()
    result = agent.handle_ar_status_change("INV-500", "OPP-1003", deal_amount=100000)
    assert result["status"] == "error"
