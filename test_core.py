from core import ApprovalQueue, EscalationQueue


def test_stage_without_dedup_key_always_creates_new():
    queue = ApprovalQueue()
    id_a, created_a = queue.stage("kind_x", {"a": 1}, "role")
    id_b, created_b = queue.stage("kind_x", {"a": 1}, "role")
    assert created_a and created_b
    assert id_a != id_b


def test_stage_with_dedup_key_returns_same_item():
    queue = ApprovalQueue()
    id_a, created_a = queue.stage("kind_x", {"a": 1}, "role", dedup_key="OPP-1")
    id_b, created_b = queue.stage("kind_x", {"a": 1}, "role", dedup_key="OPP-1")
    assert created_a is True
    assert created_b is False
    assert id_a == id_b
    assert len(queue.pending) == 1


def test_dedup_key_scoped_to_kind():
    queue = ApprovalQueue()
    id_a, _ = queue.stage("kind_x", {}, "role", dedup_key="same-key")
    id_b, _ = queue.stage("kind_y", {}, "role", dedup_key="same-key")
    assert id_a != id_b


def test_approve_removes_from_pending():
    queue = ApprovalQueue()
    item_id, _ = queue.stage("kind_x", {"a": 1}, "role")
    queue.approve(item_id, approved_by="manager")
    assert item_id not in queue.pending
    assert item_id in queue.resolved


def test_escalation_dedup_returns_open_escalation():
    queue = EscalationQueue()
    id_a, created_a = queue.raise_escalation("reason", "owner", 4, {}, dedup_key="OPP-9")
    id_b, created_b = queue.raise_escalation("reason", "owner", 4, {}, dedup_key="OPP-9")
    assert created_a is True
    assert created_b is False
    assert id_a == id_b


def test_escalation_dedup_allows_new_after_resolution():
    queue = EscalationQueue()
    id_a, _ = queue.raise_escalation("reason", "owner", 4, {}, dedup_key="OPP-9")
    queue.resolve(id_a, resolution="capacity freed up")
    id_b, created_b = queue.raise_escalation("reason", "owner", 4, {}, dedup_key="OPP-9")
    assert created_b is True
    assert id_b != id_a
