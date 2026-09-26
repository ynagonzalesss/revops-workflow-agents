from core import AuditLog, ApprovalQueue, EscalationQueue
from connectors import SalesforceConnector, NetSuiteConnector, WorkdayConnector
from fixtures import build_mock_session
from synapto import SynaptoAgent


def build_synapto():
    session = build_mock_session()
    agent = SynaptoAgent(
        AuditLog(), ApprovalQueue(), EscalationQueue(),
        SalesforceConnector(session), NetSuiteConnector(session), WorkdayConnector(session),
    )
    return agent, session


def test_certification_tags_matching_opportunity_and_updates_rate():
    agent, session = build_synapto()
    result = agent.handle_certification_update("EMP-9", "SASE_CERT", new_billable_rate=185)
    assert "OPP-1001" in result["tagged_opportunities"]
    assert session["opportunities"]["OPP-1001"]["tagged_experts"] == ["EMP-9"]
    assert session["openair_rates"]["EMP-9"] == 185


def test_rate_change_captures_previous_value_for_reversibility():
    agent, session = build_synapto()
    agent.handle_certification_update("EMP-9", "SASE_CERT", new_billable_rate=150)
    second = agent.handle_certification_update("EMP-9", "SASE_CERT", new_billable_rate=185)
    assert second["rate_change"]["previous_rate"] == 150
    assert second["rate_change"]["new_rate"] == 185


def test_repeated_tagging_does_not_duplicate_expert_entry():
    agent, session = build_synapto()
    agent.handle_certification_update("EMP-9", "SASE_CERT", new_billable_rate=150)
    agent.handle_certification_update("EMP-9", "SASE_CERT", new_billable_rate=150)
    assert session["opportunities"]["OPP-1001"]["tagged_experts"] == ["EMP-9"]


def test_skill_gap_below_threshold_does_not_alert():
    agent, _ = build_synapto()
    result = agent.check_skill_gap("SASE_CERT", pipeline_count=10, certified_headcount=9)
    assert result["status"] == "ok"


def test_skill_gap_at_or_above_threshold_alerts():
    agent, _ = build_synapto()
    result = agent.check_skill_gap("SASE_CERT", pipeline_count=12, certified_headcount=8)
    assert result["status"] == "alerted"
    assert result["gap"] == 4
    assert "escalation_id" in result
