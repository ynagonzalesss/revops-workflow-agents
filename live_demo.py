from core import AuditLog, ApprovalQueue, EscalationQueue
from connectors import NetSuiteConnector, WorkdayConnector
from connectors_live import LiveSalesforceConnector
from gatekeeper import GatekeeperAgent
from synapto import SynaptoAgent


def main():
    audit_log = AuditLog()
    approval_queue = ApprovalQueue()
    escalation_queue = EscalationQueue()

    salesforce = LiveSalesforceConnector()
    netsuite = NetSuiteConnector(session={"capacity": {}})
    workday = WorkdayConnector(session={"capacity": {"TAM-42": {"available": True, "slots": 2}}})

    gatekeeper = GatekeeperAgent(audit_log, approval_queue, escalation_queue, salesforce, netsuite, workday)
    synapto = SynaptoAgent(audit_log, approval_queue, escalation_queue, salesforce, netsuite, workday)

    opportunity_id = input("Closed-Won Opportunity Id to test Gatekeeper against: ").strip()
    print(gatekeeper.handle_closed_won(opportunity_id))

    print("\nPending approvals:")
    print(approval_queue.list_pending())

    print("\nAudit log:")
    print(audit_log.dump())


if __name__ == "__main__":
    main()
