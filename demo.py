from core import AuditLog, ApprovalQueue, EscalationQueue
from connectors import SalesforceConnector, NetSuiteConnector, WorkdayConnector
from fixtures import build_mock_session
from gatekeeper import GatekeeperAgent
from ledgify import LedgifyAgent
from synapto import SynaptoAgent


def main():
    session = build_mock_session()
    audit_log = AuditLog()
    approval_queue = ApprovalQueue()
    escalation_queue = EscalationQueue()

    salesforce = SalesforceConnector(session)
    netsuite = NetSuiteConnector(session)
    workday = WorkdayConnector(session)

    gatekeeper = GatekeeperAgent(audit_log, approval_queue, escalation_queue, salesforce, netsuite, workday)
    ledgify = LedgifyAgent(audit_log, approval_queue, escalation_queue, salesforce, netsuite, workday)
    synapto = SynaptoAgent(audit_log, approval_queue, escalation_queue, salesforce, netsuite, workday)

    print("--- Gatekeeper: clean, capacity available ---")
    print(gatekeeper.handle_closed_won("OPP-1001"))

    print("\n--- Gatekeeper: bad SKU / bad dates ---")
    print(gatekeeper.handle_closed_won("OPP-1002"))

    print("\n--- Gatekeeper: capacity gate triggers escalation ---")
    print(gatekeeper.handle_closed_won("OPP-1003"))

    print("\n--- Ledgify: AR cleared, commission staged (not posted) ---")
    result = ledgify.handle_ar_status_change("INV-500", "OPP-1001", deal_amount=300000)
    print(result)

    print("\n--- Ledgify: Finance approves one staged line, only then it posts ---")
    first_approval_id = result["approval_ids"][0]
    print(ledgify.post_approved_line(first_approval_id, approved_by="finance_manager_1"))

    print("\n--- Synapto: certification triggers routing + versioned rate update ---")
    print(synapto.handle_certification_update("EMP-9", "SASE_CERT", new_billable_rate=185))

    print("\n--- Synapto: skill gap alert ---")
    print(synapto.check_skill_gap("SASE_CERT", pipeline_count=12, certified_headcount=8))

    print("\n--- Pending approvals remaining ---")
    print(approval_queue.list_pending())

    print("\n--- Audit log ---")
    print(audit_log.dump())


if __name__ == "__main__":
    main()
