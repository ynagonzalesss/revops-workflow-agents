"""Approvals must only unlock the exact thing they were staged for."""
import pytest

from core import AuditLog, ApprovalQueue, ApprovalError, EscalationQueue
from connectors import SalesforceConnector, NetSuiteConnector, WorkdayConnector
from fixtures import build_mock_session
from gatekeeper import GatekeeperAgent
from ledgify import LedgifyAgent


def build_agents():
    session = build_mock_session()
    shared = (AuditLog(), ApprovalQueue(), EscalationQueue())
    systems = (SalesforceConnector(session), NetSuiteConnector(session), WorkdayConnector(session))
    return GatekeeperAgent(*shared, *systems), LedgifyAgent(*shared, *systems), session


def test_commission_approval_cannot_unfreeze_provisioning():
    gatekeeper, ledgify, _ = build_agents()
    commission_id = ledgify.handle_ar_status_change("INV-500", "OPP-1001", deal_amount=300000)["approval_ids"][0]
    with pytest.raises(ApprovalError, match="commission_line"):
        gatekeeper.unfreeze_provisioning("OPP-1003", commission_id, approved_by="someone")
    assert commission_id in gatekeeper.approval_queue.pending


def test_billing_approval_cannot_unfreeze_a_different_opportunity():
    gatekeeper, _, _ = build_agents()
    approval_id = gatekeeper.handle_closed_won("OPP-1001")["approval_id"]
    with pytest.raises(ApprovalError, match="opportunity_id"):
        gatekeeper.unfreeze_provisioning("OPP-1003", approval_id, approved_by="deal_desk_1")
    assert approval_id in gatekeeper.approval_queue.pending


def test_matching_billing_approval_unfreezes():
    gatekeeper, _, _ = build_agents()
    approval_id = gatekeeper.handle_closed_won("OPP-1001")["approval_id"]
    result = gatekeeper.unfreeze_provisioning("OPP-1001", approval_id, approved_by="deal_desk_1")
    assert result["status"] == "provisioning_unfrozen"
    assert gatekeeper.approval_queue.resolved[approval_id]["status"] == "approved"


def test_wrong_kind_is_rejected_before_anything_changes():
    gatekeeper, ledgify, session = build_agents()
    billing_id = gatekeeper.handle_closed_won("OPP-1001")["approval_id"]
    with pytest.raises(ApprovalError, match="billing_schedule"):
        ledgify.post_approved_line(billing_id, approved_by="finance_manager_1")
    # The item is still pending and nothing reached Workday.
    assert billing_id in ledgify.approval_queue.pending
    assert "staged_compensation" not in session


def test_approving_twice_gives_a_clear_error():
    gatekeeper, _, _ = build_agents()
    approval_id = gatekeeper.handle_closed_won("OPP-1001")["approval_id"]
    gatekeeper.unfreeze_provisioning("OPP-1001", approval_id, approved_by="deal_desk_1")
    with pytest.raises(ApprovalError, match="already resolved"):
        gatekeeper.unfreeze_provisioning("OPP-1001", approval_id, approved_by="deal_desk_1")


def test_unknown_approval_id_gives_a_clear_error():
    queue = ApprovalQueue()
    with pytest.raises(ApprovalError, match="unknown"):
        queue.approve("no-such-id", approved_by="x")
