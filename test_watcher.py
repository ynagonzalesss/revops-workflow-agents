"""The Salesforce watcher, driven by a fake Salesforce client (no network or credentials)."""
from datetime import datetime, timezone

import pytest

pytest.importorskip("simple_salesforce")
from simple_salesforce.exceptions import SalesforceMalformedRequest

from connectors_live import LiveSalesforceConnector
from watch_salesforce import ClosedWonWatcher, build_gatekeeper


def make_opp(opp_id, tam="TAM-42", sku="SASE-2200", modstamp="2026-09-26T17:40:00.000+0000"):
    return {
        "Id": opp_id, "Name": f"Deal {opp_id}", "StageName": "Closed Won", "SystemModstamp": modstamp,
        "SKU__c": sku, "Subscription_Start__c": "2026-10-01", "Subscription_End__c": "2027-10-01",
        "TAM_Id__c": tam, "Term_Months__c": 12.0, "Required_Skills__c": None,
    }


class FakeOpportunityApi:
    def __init__(self, client):
        self.client = client

    def get(self, opp_id):
        return self.client.opps[opp_id]

    def update(self, opp_id, fields):
        if self.client.status_field_missing:
            raise SalesforceMalformedRequest("url", 400, "Opportunity", b"No such column 'Gatekeeper_Status__c'")
        self.client.opps[opp_id].update(fields)
        self.client.opps[opp_id]["SystemModstamp"] = "2026-09-26T17:41:00.000+0000"  # a write bumps it
        self.client.writes.append((opp_id, fields))


class FakeClient:
    def __init__(self, *opps, status_field_missing=False):
        self.opps = {o["Id"]: o for o in opps}
        self.writes = []
        self.status_field_missing = status_field_missing
        self.Opportunity = FakeOpportunityApi(self)

    def query(self, soql):
        if "FROM OpportunityLineItem" in soql:
            return {"records": []}
        return {"records": [o for o in self.opps.values() if o["StageName"] == "Closed Won"]}


def build_watcher(client, writeback=True):
    salesforce = LiveSalesforceConnector(client=client)
    start = datetime(2026, 9, 26, 17, 0, tzinfo=timezone.utc)
    return ClosedWonWatcher(salesforce, build_gatekeeper(salesforce), writeback=writeback,
                            start_from=start, out=lambda *_: None)


def test_closed_won_deal_is_staged_and_status_written_back():
    client = FakeClient(make_opp("006A"))
    results = build_watcher(client).poll_once()
    assert results[0]["result"]["status"] == "staged"
    assert client.opps["006A"]["Gatekeeper_Status__c"].startswith("STAGED")


def test_no_capacity_is_escalated():
    client = FakeClient(make_opp("006B", tam="TAM-07"))
    results = build_watcher(client).poll_once()
    assert results[0]["result"]["status"] == "gated"
    assert client.opps["006B"]["Gatekeeper_Status__c"].startswith("ESCALATED")


def test_bad_sku_is_blocked():
    client = FakeClient(make_opp("006C", sku="oops"))
    results = build_watcher(client).poll_once()
    assert results[0]["result"]["status"] == "blocked"
    assert "sku" in client.opps["006C"]["Gatekeeper_Status__c"]


def test_own_status_write_does_not_retrigger():
    client = FakeClient(make_opp("006A"))
    watcher = build_watcher(client)
    watcher.poll_once()
    assert watcher.poll_once() == []   # the write bumped SystemModstamp, but nothing relevant changed
    assert len(client.writes) == 1


def test_fixing_a_blocked_deal_reprocesses_it():
    client = FakeClient(make_opp("006C", sku="oops"))
    watcher = build_watcher(client)
    assert watcher.poll_once()[0]["result"]["status"] == "blocked"
    client.opps["006C"]["SKU__c"] = "SASE-2200"
    assert watcher.poll_once()[0]["result"]["status"] == "staged"


def test_cursor_advances_to_latest_modification():
    client = FakeClient(make_opp("006A", modstamp="2026-09-26T17:45:30.250+0000"))
    watcher = build_watcher(client, writeback=False)
    watcher.poll_once()
    assert watcher.cursor == datetime(2026, 9, 26, 17, 45, 30, tzinfo=timezone.utc)


def test_missing_status_field_falls_back_to_print_only():
    client = FakeClient(make_opp("006A"), status_field_missing=True)
    watcher = build_watcher(client)
    results = watcher.poll_once()
    assert results[0]["result"]["status"] == "staged"   # the agent still ran
    assert watcher.writeback is False
