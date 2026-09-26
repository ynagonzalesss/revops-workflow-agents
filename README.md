# Gatekeeper · Ledgify · Synapto

Three workflow agents that sit between a CRM (Salesforce), an ERP (NetSuite) and an HR system (Workday) and handle the hand-offs that usually go wrong in a subscription business: a deal closes before anyone checks delivery capacity, commissions are paid on invoices that haven't cleared, or a newly certified engineer isn't routed to the deals that need them.

The main design rule: **an agent can prepare a change, but a person approves it before it touches a system of record.** Every action is written to an audit log, and every block is surfaced as a named escalation with an owner and an SLA, not a silent failure.

## The agents

| Agent | Trigger | What it does | Human checkpoint |
|---|---|---|---|
| **Gatekeeper** | Opportunity marked Closed Won | Validates quote fields (SKU, subscription dates), checks delivery capacity in Workday, drafts a NetSuite billing schedule | Deal Desk approves the billing schedule before provisioning is unfrozen. No capacity → escalation to Delivery Ops with a 4-hour SLA |
| **Ledgify** | Invoice status changes in NetSuite | Once the invoice is **Paid**, computes commission (tiers, accelerator, split credit) and stages one line per rep | Finance/HR approves each line before it's posted to Workday |
| **Synapto** | Employee gains a certification | Tags the employee on open opportunities that need that skill, updates their billable rate | None by design (low-risk, reversible). Every rate change records the previous rate so it can be rolled back from the audit log |

## Why there's no LLM in the loop

These are deterministic, event-driven agents, and that's intentional. Commission payouts, billing schedules and provisioning are decisions where you need the same answer every time and a clear explanation of why. A language model adds variability without adding value there. If I extended this, the places where AI would earn its place are the fuzzy inputs: reading free-text deal notes to infer required skills, or drafting the escalation message a human reads.

## Design decisions worth pointing out

- **Stage, don't execute.** `ApprovalQueue` is the only path to a write. `approve()` checks that the item is still pending, is the expected kind, and belongs to the record being acted on, *before* changing anything. A commission approval can't unfreeze a deal, and one deal's approval can't unfreeze another.
- **Idempotent on retries.** Webhooks fire more than once. Staged approvals and open escalations are deduplicated by a key (opportunity ID, or invoice + employee), so a repeated event never double-stages a payout.
- **Fail loudly, not wrongly.** A commission plan whose splits don't sum to 100%, or that has no tiers, raises an error instead of computing a wrong number. Blank or malformed quote fields are reported as validation errors. Source-system outages come back as a logged `source_system_error` rather than a crash.
- **Same contract for mock and live connectors.** "Record not found" returns `None` from both, so agent logic doesn't change when you swap in a real API.

## Project layout

```
core.py              Audit log, approval queue, escalation queue, BaseAgent
connectors.py        Mock Salesforce / NetSuite / Workday connectors + quote validation
connectors_live.py   Real Salesforce connector (simple-salesforce), with retries and error mapping
gatekeeper.py        Gatekeeper agent
ledgify.py           Ledgify agent + compute_commission()
synapto.py           Synapto agent
fixtures.py          Mock data used by the demo and tests
demo.py              End-to-end run on mock data, no credentials needed
live_demo.py         Gatekeeper against a real Salesforce org
test_*.py            Test suite
```

## Run it

```
pip install -r requirements.txt -r requirements-dev.txt
python3 demo.py          # full walkthrough on mock data
python3 -m pytest -v     # 44 tests
```

The tests cover commission edge cases (accelerators, bad splits, missing tiers), quote validation (including blank fields from a live system), duplicate-event handling, approval checks, and the live connector's not-found behaviour using a fake client.

## Running against a real Salesforce org (optional)

1. Sign up for a free [Salesforce Developer Edition](https://developer.salesforce.com/signup) org.
2. Reset your security token (profile → Settings → My Personal Information → Reset My Security Token). It's emailed to you.
3. Create the custom fields the connector reads (Setup → Object Manager):

   **On Opportunity**
   - `TAM_Id__c` (Text): assigned TAM / delivery squad
   - `SKU__c` (Text)
   - `Subscription_Start__c`, `Subscription_End__c` (Date)
   - `Term_Months__c` (Number)
   - `Required_Skills__c` (Multi-Select Picklist, e.g. `SASE_CERT`)
   - `Tagged_Expert__c` (Text): written by Synapto

   **On Opportunity Product (OpportunityLineItem)**
   - `Product_SKU__c` (Text)

   **Custom object `Commission_Plan__c`** (only needed for Ledgify)
   - `Opportunity__c` (Lookup → Opportunity)
   - `Employee_Id__c` (Text)
   - `Tier_Json__c`, `Accelerator_Json__c`, `Splits_Json__c` (Long Text), e.g. `[{"threshold": 0, "rate": 0.05}]`

4. Add your credentials:
   ```
   cp .env.example .env     # fill in real values; .env is git-ignored
   export $(cat .env | xargs)
   python3 test_connection.py   # confirms auth and lists a few Opportunities
   ```
5. Create a Closed Won Opportunity with those fields filled in, then run `python3 live_demo.py` and paste its Id.

NetSuite and Workday stay mocked because neither offers free developer access.

**Status:** the live connector is tested against a fake client but hasn't yet been run end-to-end against a real org.

## Known limitations

- **In-memory state.** Approval and escalation queues are gone when the process exits. Production would need a database and a real notification channel (Slack/email).
- **No authorization on approvals.** Each staged item records an `approver_role`, but nothing yet checks that the caller holds it.
- **Events are called manually.** In production these would be wired to Salesforce Platform Events / Change Data Capture, NetSuite scripts or webhooks, and Workday business-process notifications.
- **Placeholder schema.** Field names and the SKU format (`QUOTE_FIELD_RULES`) are illustrative and would need to match a real org's schema.
- **Commission tiers are whole-deal, not marginal.** Crossing a threshold applies the higher rate to the entire deal amount. Many real plans apply it only to the portion above the threshold.
- **`Tagged_Expert__c` holds one value**, so in the live connector a newly tagged expert replaces the previous one. The mock keeps a list.
- **Skill-gap escalations aren't deduplicated yet**, and a rejected approval can't be re-staged for the same key.

## License

© 2026 Czarina Mari Gonzales. All rights reserved. Shared for portfolio viewing only; no permission is granted to copy, modify, or reuse this code. See [LICENSE](LICENSE).
