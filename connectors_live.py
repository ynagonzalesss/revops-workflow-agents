import json
import os

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from simple_salesforce import Salesforce
from simple_salesforce.exceptions import (
    SalesforceAuthenticationFailed,
    SalesforceError,
    SalesforceResourceNotFound,
)

from connectors import ConnectorError


class SalesforceConnectorError(ConnectorError):
    pass


REQUIRED_ENV_VARS = ("SF_USERNAME", "SF_PASSWORD", "SF_SECURITY_TOKEN")


def build_retrying_session():
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=(429, 500, 502, 503, 504))
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def connect_from_env():
    missing = [name for name in REQUIRED_ENV_VARS if not os.environ.get(name)]
    if missing:
        raise SalesforceConnectorError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "Copy .env.example to .env, fill in real values, and export them before running."
        )
    try:
        return Salesforce(
            username=os.environ["SF_USERNAME"],
            password=os.environ["SF_PASSWORD"],
            security_token=os.environ["SF_SECURITY_TOKEN"],
            domain=os.environ.get("SF_DOMAIN", "login"),
            session=build_retrying_session(),
        )
    except SalesforceAuthenticationFailed as error:
        raise SalesforceConnectorError(
            f"Salesforce authentication failed: {error}. Check SF_USERNAME/SF_PASSWORD/SF_SECURITY_TOKEN "
            "and confirm the security token is current (resetting your password invalidates it)."
        ) from error
    except requests.exceptions.RequestException as error:
        raise SalesforceConnectorError(f"Could not reach Salesforce: {error}") from error


def escape_soql(value):
    return value.replace("\\", "\\\\").replace("'", "\\'")


class LiveSalesforceConnector:
    def __init__(self, client=None):
        self.client = client or connect_from_env()

    def get_closed_won_opportunity(self, opportunity_id):
        try:
            record = self.client.Opportunity.get(opportunity_id)
        except SalesforceResourceNotFound:
            # Same contract as the mock connector: "not found" is a normal outcome, not an exception.
            return None
        except SalesforceError as error:
            raise SalesforceConnectorError(
                f"Salesforce API error fetching Opportunity {opportunity_id}: {error}"
            ) from error
        except requests.exceptions.RequestException as error:
            raise SalesforceConnectorError(f"Network error fetching Opportunity {opportunity_id}: {error}") from error

        line_items = self._get_line_item_skus(opportunity_id)
        required_skills = self._split_multipicklist(record.get("Required_Skills__c"))
        return {
            "id": record["Id"],
            "tam_id": record.get("TAM_Id__c"),
            "sku": record.get("SKU__c"),
            "subscription_start": record.get("Subscription_Start__c"),
            "subscription_end": record.get("Subscription_End__c"),
            "term_months": record.get("Term_Months__c"),
            "line_items": line_items,
            "required_skills": required_skills,
        }

    def _get_line_item_skus(self, opportunity_id):
        query = (
            "SELECT Id, Product_SKU__c FROM OpportunityLineItem "
            f"WHERE OpportunityId = '{escape_soql(opportunity_id)}'"
        )
        result = self._run_query(query, context=f"line items for Opportunity {opportunity_id}")
        return [r["Product_SKU__c"] for r in result["records"] if r.get("Product_SKU__c")]

    def _split_multipicklist(self, value):
        return value.split(";") if value else []

    def _run_query(self, query, context):
        try:
            return self.client.query(query)
        except SalesforceError as error:
            raise SalesforceConnectorError(f"Salesforce query failed ({context}): {error}") from error
        except requests.exceptions.RequestException as error:
            raise SalesforceConnectorError(f"Network error querying Salesforce ({context}): {error}") from error

    def get_opportunities_requiring_skill(self, skill):
        query = (
            "SELECT Id, Name, Required_Skills__c FROM Opportunity "
            f"WHERE Required_Skills__c INCLUDES ('{escape_soql(skill)}')"
        )
        result = self._run_query(query, context=f"opportunities requiring skill {skill}")
        return [
            {"id": r["Id"], "required_skills": self._split_multipicklist(r.get("Required_Skills__c"))}
            for r in result["records"]
        ]

    def tag_qualified_rep(self, opportunity_id, employee_id):
        try:
            self.client.Opportunity.update(opportunity_id, {"Tagged_Expert__c": employee_id})
        except SalesforceResourceNotFound as error:
            raise SalesforceConnectorError(f"Opportunity {opportunity_id} not found") from error
        except SalesforceError as error:
            raise SalesforceConnectorError(
                f"Salesforce API error tagging Opportunity {opportunity_id}: {error}"
            ) from error
        except requests.exceptions.RequestException as error:
            raise SalesforceConnectorError(f"Network error tagging Opportunity {opportunity_id}: {error}") from error
        return {"opportunity_id": opportunity_id, "tagged_expert": employee_id}

    def get_commission_plan(self, opportunity_id):
        query = (
            "SELECT Id, Employee_Id__c, Tier_Json__c, Accelerator_Json__c, Splits_Json__c "
            f"FROM Commission_Plan__c WHERE Opportunity__c = '{escape_soql(opportunity_id)}'"
        )
        result = self._run_query(query, context=f"commission plan for Opportunity {opportunity_id}")
        if not result["records"]:
            return None
        record = result["records"][0]
        try:
            return {
                "employee_id": record["Employee_Id__c"],
                "tiers": json.loads(record["Tier_Json__c"]),
                "accelerator": json.loads(record["Accelerator_Json__c"]) if record.get("Accelerator_Json__c") else None,
                "splits": json.loads(record["Splits_Json__c"]) if record.get("Splits_Json__c") else None,
            }
        except (KeyError, json.JSONDecodeError) as error:
            raise SalesforceConnectorError(
                f"Commission_Plan__c record for Opportunity {opportunity_id} is missing or has malformed JSON "
                f"fields: {error}"
            ) from error
