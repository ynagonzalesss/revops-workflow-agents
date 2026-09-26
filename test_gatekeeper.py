from core import AuditLog, ApprovalQueue, EscalationQueue
from connectors import SalesforceConnector, NetSuiteConnector, WorkdayConnector
from fixtures import build_mock_session
from gatekeeper import GatekeeperAgent


def build_gatekeeper():
    session = build_mock_session()
    agent = GatekeeperAgent(
        AuditLog(), ApprovalQueue(), EscalationQueue(),
        SalesforceConnector(session), NetSuiteConnector(session), WorkdayConnector(session),
    )
    return agent, session


def test_clean_opportunity_with_capacity_gets_staged():
    agent, _ = build_gatekeeper()
    result = agent.handle_closed_won("OPP-1001")
    assert result["status"] == "staged"
    assert "approval_id" in result


def test_bad_sku_and_dates_are_blocked():
    agent, _ = build_gatekeeper()
    result = agent.handle_closed_won("OPP-1002")
    assert result["status"] == "blocked"
    assert any("sku" in e for e in result["errors"])
    assert any("subscription_start" in e for e in result["errors"])


def test_insufficient_capacity_escalates_instead_of_blocking_silently():
    agent, _ = build_gatekeeper()
    result = agent.handle_closed_won("OPP-1003")
    assert result["status"] == "gated"
    assert result["reason"] == "insufficient_capacity"
    assert "escalation_id" in result


def test_repeated_closed_won_event_does_not_double_stage():
    agent, _ = build_gatekeeper()
    first = agent.handle_closed_won("OPP-1001")
    second = agent.handle_closed_won("OPP-1001")
    assert first["approval_id"] == second["approval_id"]
    assert len(agent.approval_queue.pending) == 1


def test_repeated_capacity_gate_does_not_double_escalate():
    agent, _ = build_gatekeeper()
    first = agent.handle_closed_won("OPP-1003")
    second = agent.handle_closed_won("OPP-1003")
    assert first["escalation_id"] == second["escalation_id"]
    assert len(agent.escalation_queue.open_escalations) == 1


def test_unknown_opportunity_returns_error():
    agent, _ = build_gatekeeper()
    result = agent.handle_closed_won("OPP-DOES-NOT-EXIST")
    assert result["status"] == "error"


class FailingSalesforce:
    def get_closed_won_opportunity(self, opportunity_id):
        from connectors import ConnectorError
        raise ConnectorError("Salesforce is down")


def test_source_system_error_is_returned_and_logged_not_raised():
    session = build_mock_session()
    agent = GatekeeperAgent(
        AuditLog(), ApprovalQueue(), EscalationQueue(),
        FailingSalesforce(), NetSuiteConnector(session), WorkdayConnector(session),
    )
    result = agent.handle_closed_won("OPP-1001")
    assert result["status"] == "error"
    assert result["reason"] == "source_system_error"
    assert agent.audit_log.entries[-1]["action"] == "source_system_error"
