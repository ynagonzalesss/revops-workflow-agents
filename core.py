import json
import time
import uuid
from dataclasses import dataclass, field


@dataclass
class AuditLog:
    entries: list = field(default_factory=list)

    def record(self, agent, action, payload):
        entry = {
            "id": str(uuid.uuid4()),
            "timestamp": time.time(),
            "agent": agent,
            "action": action,
            "payload": payload,
        }
        self.entries.append(entry)
        return entry

    def for_agent(self, agent):
        return [e for e in self.entries if e["agent"] == agent]

    def dump(self):
        return json.dumps(self.entries, indent=2, default=str)


class ApprovalError(Exception):
    """Raised when an approval call doesn't match the item it points at. Nothing is changed."""


@dataclass
class ApprovalQueue:
    pending: dict = field(default_factory=dict)
    resolved: dict = field(default_factory=dict)
    _dedup_index: dict = field(default_factory=dict)

    def find_by_dedup_key(self, kind, dedup_key):
        return self._dedup_index.get((kind, dedup_key))

    def stage(self, kind, payload, approver_role, dedup_key=None):
        if dedup_key is not None:
            existing_id = self._dedup_index.get((kind, dedup_key))
            if existing_id is not None:
                return existing_id, False

        item_id = str(uuid.uuid4())
        self.pending[item_id] = {
            "id": item_id,
            "kind": kind,
            "payload": payload,
            "approver_role": approver_role,
            "staged_at": time.time(),
            "dedup_key": dedup_key,
        }
        if dedup_key is not None:
            self._dedup_index[(kind, dedup_key)] = item_id
        return item_id, True

    def _checked_pending_item(self, item_id, expected_kind=None, expected_payload=None):
        item = self.pending.get(item_id)
        if item is None:
            state = "already resolved" if item_id in self.resolved else "unknown"
            raise ApprovalError(f"Approval item {item_id} is {state}, not pending")
        if expected_kind is not None and item["kind"] != expected_kind:
            raise ApprovalError(
                f"Approval item {item_id} is a '{item['kind']}', expected '{expected_kind}'"
            )
        for key, value in (expected_payload or {}).items():
            if item["payload"].get(key) != value:
                raise ApprovalError(
                    f"Approval item {item_id} has {key}={item['payload'].get(key)!r}, expected {value!r}"
                )
        return item

    def approve(self, item_id, approved_by, expected_kind=None, expected_payload=None):
        # Every check runs before anything is mutated, so a bad call leaves the item pending.
        self._checked_pending_item(item_id, expected_kind, expected_payload)
        item = self.pending.pop(item_id)
        item["approved_by"] = approved_by
        item["resolved_at"] = time.time()
        item["status"] = "approved"
        self.resolved[item_id] = item
        return item

    def reject(self, item_id, rejected_by, reason):
        self._checked_pending_item(item_id)
        item = self.pending.pop(item_id)
        item["rejected_by"] = rejected_by
        item["resolved_at"] = time.time()
        item["status"] = "rejected"
        item["reason"] = reason
        self.resolved[item_id] = item
        return item

    def list_pending(self, kind=None):
        items = list(self.pending.values())
        if kind:
            items = [i for i in items if i["kind"] == kind]
        return items


@dataclass
class EscalationQueue:
    open_escalations: dict = field(default_factory=dict)
    _dedup_index: dict = field(default_factory=dict)

    def find_open_by_dedup_key(self, reason, dedup_key):
        esc_id = self._dedup_index.get((reason, dedup_key))
        if esc_id is not None and esc_id in self.open_escalations:
            return esc_id
        return None

    def raise_escalation(self, reason, owner, sla_hours, payload, dedup_key=None):
        if dedup_key is not None:
            existing = self.find_open_by_dedup_key(reason, dedup_key)
            if existing is not None:
                return existing, False

        esc_id = str(uuid.uuid4())
        self.open_escalations[esc_id] = {
            "id": esc_id,
            "reason": reason,
            "owner": owner,
            "sla_deadline": time.time() + sla_hours * 3600,
            "payload": payload,
            "status": "open",
            "dedup_key": dedup_key,
        }
        if dedup_key is not None:
            self._dedup_index[(reason, dedup_key)] = esc_id
        return esc_id, True

    def resolve(self, esc_id, resolution):
        esc = self.open_escalations.pop(esc_id)
        esc["status"] = "resolved"
        esc["resolution"] = resolution
        return esc

    def breached(self):
        now = time.time()
        return [e for e in self.open_escalations.values() if e["sla_deadline"] < now]


class BaseAgent:
    name = "base_agent"

    def __init__(self, audit_log, approval_queue, escalation_queue):
        self.audit_log = audit_log
        self.approval_queue = approval_queue
        self.escalation_queue = escalation_queue

    def log(self, action, payload):
        return self.audit_log.record(self.name, action, payload)

    def stage_for_approval(self, kind, payload, approver_role, dedup_key=None):
        item_id, created = self.approval_queue.stage(kind, payload, approver_role, dedup_key=dedup_key)
        if created:
            self.log("staged_for_approval", {"item_id": item_id, "kind": kind, "payload": payload})
        else:
            self.log("duplicate_stage_skipped", {"item_id": item_id, "kind": kind, "dedup_key": dedup_key})
        return item_id

    def escalate(self, reason, owner, sla_hours, payload, dedup_key=None):
        esc_id, created = self.escalation_queue.raise_escalation(reason, owner, sla_hours, payload, dedup_key=dedup_key)
        if created:
            self.log("escalated", {"escalation_id": esc_id, "reason": reason, "owner": owner})
        else:
            self.log("duplicate_escalation_skipped", {"escalation_id": esc_id, "reason": reason, "dedup_key": dedup_key})
        return esc_id
