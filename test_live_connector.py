"""Live Salesforce connector behaviour, using a fake client (no network or credentials)."""
import pytest

pytest.importorskip("simple_salesforce")
from simple_salesforce.exceptions import SalesforceResourceNotFound

from connectors_live import LiveSalesforceConnector


class FakeOpportunityApi:
    def get(self, opportunity_id):
        raise SalesforceResourceNotFound("url", 404, "Opportunity", b"not found")


class FakeClient:
    Opportunity = FakeOpportunityApi()


def test_missing_opportunity_returns_none_like_the_mock():
    connector = LiveSalesforceConnector(client=FakeClient())
    assert connector.get_closed_won_opportunity("006XXXXXXXXXXXX") is None
