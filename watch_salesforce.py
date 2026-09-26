"""Watch a real Salesforce org and run Gatekeeper the moment a deal is marked Closed Won.

    python3 watch_salesforce.py                 # check every 5 seconds
    python3 watch_salesforce.py --interval 10   # slower polling
    python3 watch_salesforce.py --no-writeback  # print only, don't write status to Salesforce

Mark an Opportunity "Closed Won" in Salesforce and, within a few seconds, Gatekeeper
validates it, checks delivery capacity, and either stages it for approval, blocks it, or
escalates it. The outcome is printed here and written back to the Opportunity's
Gatekeeper_Status__c field, so you can watch it appear in Salesforce itself.

NetSuite and Workday are still simulated. Delivery capacity comes from DEMO_CAPACITY below:
set an Opportunity's TAM_Id__c to TAM-42 to see it staged, or TAM-07 to see an escalation.
"""
import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone

from connectors import NetSuiteConnector, WorkdayConnector
from connectors_live import LiveSalesforceConnector, SalesforceConnectorError
from core import AuditLog, ApprovalQueue, EscalationQueue
from gatekeeper import GatekeeperAgent

DEMO_CAPACITY = {
    "TAM-42": {"available": True, "slots": 2},
    "TAM-07": {"available": False, "slots": 0},
}

_USE_COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
COLORS = {"staged": "32", "blocked": "31", "gated": "33", "error": "35", "dim": "2", "bold": "1"}


def paint(text, style):
    return f"\033[{COLORS[style]}m{text}\033[0m" if _USE_COLOR else text


def describe(result):
    """Turn a Gatekeeper result into (style, one-line status) for the terminal and Salesforce."""
    status = result["status"]
    if status == "staged":
        return "staged", "STAGED: billing schedule drafted, waiting for Deal Desk approval"
    if status == "blocked":
        return "blocked", "BLOCKED: " + "; ".join(result.get("errors", []))
    if status == "gated":
        return "gated", "ESCALATED: no delivery capacity; Delivery Ops owns it, 4h SLA"
    return "error", f"ERROR: {result.get('detail') or result.get('reason')}"


def parse_sf_datetime(value):
    # e.g. "2026-09-26T17:40:00.000+0000"
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%f%z")


class ClosedWonWatcher:
    def __init__(self, salesforce, gatekeeper, writeback=True, start_from=None, out=print):
        self.salesforce = salesforce
        self.gatekeeper = gatekeeper
        self.writeback = writeback
        self.cursor = start_from or datetime.now(timezone.utc)
        self.seen = {}  # opportunity id -> fingerprint of the fields Gatekeeper cares about
        self.out = out

    def poll_once(self):
        """Check for new or changed Closed Won deals and run Gatekeeper on each. Returns results."""
        changed = self.salesforce.get_closed_won_modified_since(self.cursor)
        results = []
        for opp in changed:
            self.cursor = max(self.cursor, parse_sf_datetime(opp["modified_at"]).replace(microsecond=0))
            # Skip if nothing Gatekeeper cares about changed. This also stops our own status
            # write-back (which bumps SystemModstamp) from re-triggering the same deal forever.
            if self.seen.get(opp["id"]) == opp["fingerprint"]:
                continue
            self.seen[opp["id"]] = opp["fingerprint"]
            results.append(self._process(opp))
        return results

    def _process(self, opp):
        stamp = datetime.now().strftime("%H:%M:%S")
        self.out(f"\n{paint(stamp, 'dim')}  {paint('Closed Won detected', 'bold')}: {opp['name']} ({opp['id']})")
        result = self.gatekeeper.handle_closed_won(opp["id"])
        style, status_text = describe(result)
        self.out(f"          {paint(status_text, style)}")
        if self.writeback:
            try:
                self.salesforce.set_gatekeeper_status(opp["id"], status_text)
                self.out(paint("          ↳ written to Gatekeeper_Status__c in Salesforce", "dim"))
            except SalesforceConnectorError as error:
                self.writeback = False
                self.out(paint(f"          ↳ could not write back ({error}). "
                               "Create the Gatekeeper_Status__c field to enable this; "
                               "continuing in print-only mode.", "error"))
        return {"opportunity_id": opp["id"], "result": result, "status_text": status_text}


def build_gatekeeper(salesforce):
    audit_log, approvals, escalations = AuditLog(), ApprovalQueue(), EscalationQueue()
    gatekeeper = GatekeeperAgent(
        audit_log, approvals, escalations,
        salesforce, NetSuiteConnector(session={}), WorkdayConnector(session={"capacity": DEMO_CAPACITY}),
    )
    return gatekeeper


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--interval", type=float, default=5, help="seconds between checks (default 5)")
    parser.add_argument("--lookback-minutes", type=float, default=1,
                        help="also pick up deals closed this many minutes before starting (default 1)")
    parser.add_argument("--no-writeback", action="store_true", help="don't write status back to Salesforce")
    args = parser.parse_args()

    try:
        salesforce = LiveSalesforceConnector()
    except SalesforceConnectorError as error:
        sys.exit(f"Could not connect to Salesforce: {error}")

    gatekeeper = build_gatekeeper(salesforce)
    watcher = ClosedWonWatcher(
        salesforce, gatekeeper, writeback=not args.no_writeback,
        start_from=datetime.now(timezone.utc) - timedelta(minutes=args.lookback_minutes),
    )

    print(paint("Gatekeeper is watching Salesforce for Closed Won deals.", "bold"))
    print(paint(f"Checking every {args.interval:g}s. Press Ctrl+C to stop.", "dim"))
    try:
        while True:
            try:
                watcher.poll_once()
            except SalesforceConnectorError as error:
                print(paint(f"Salesforce check failed, will retry: {error}", "error"))
            time.sleep(args.interval)
    except KeyboardInterrupt:
        audit = gatekeeper.audit_log.entries
        pending = gatekeeper.approval_queue.list_pending()
        escalations = gatekeeper.escalation_queue.open_escalations
        print(paint(f"\nStopped. {len(audit)} audit entries, {len(pending)} pending approvals, "
                    f"{len(escalations)} open escalations this session.", "bold"))


if __name__ == "__main__":
    main()
