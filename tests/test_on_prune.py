"""on_prune namespace forwarding: pruned messages reach the hook with the app's namespace."""
import uuid

import pytest
from agentstate_reducer import MessageReducer, ReducerConfig

from test_persistence import make, build_messages


def _capture():
    seen = []
    return seen, (lambda pruned, ns: seen.append((list(pruned), ns)))


def test_hook_receives_namespace_from_state():
    seen, hook = _capture()
    reducer = MessageReducer(config=ReducerConfig(min_messages=4, max_messages=6, preserve_first=False, on_prune=[hook]))
    p = make(reducer=reducer, messages_key="messages")
    fid = str(uuid.uuid4())
    p.save_state(fid, "step", {"id": fid, "memory_namespace": "/user/kamal", "messages": build_messages(5)})
    assert len(seen) == 1
    pruned, ns = seen[0]
    assert ns == "/user/kamal"
    assert [m["content"] for m in pruned] == ["msg 0", "reply 0", "msg 1", "reply 1", "msg 2", "reply 2"]
    assert len(p.load_state(fid)["messages"]) == 4          # surviving persisted


def test_namespace_falls_back_to_flow_scope():
    seen, hook = _capture()
    reducer = MessageReducer(config=ReducerConfig(min_messages=4, max_messages=6, preserve_first=False, on_prune=[hook]))
    p = make(reducer=reducer, messages_key="messages")
    fid = str(uuid.uuid4())
    p.save_state(fid, "step", {"id": fid, "messages": build_messages(5)})
    assert seen and seen[0][1] == f"/flow/{fid}"


def test_custom_namespace_key():
    seen, hook = _capture()
    reducer = MessageReducer(config=ReducerConfig(min_messages=4, max_messages=6, preserve_first=False, on_prune=[hook], namespace_key="tenant"))
    p = make(reducer=reducer, messages_key="messages")
    fid = str(uuid.uuid4())
    p.save_state(fid, "step", {"id": fid, "tenant": "/acme", "messages": build_messages(5)})
    assert seen and seen[0][1] == "/acme"


def test_no_prune_no_hook():
    seen, hook = _capture()
    reducer = MessageReducer(config=ReducerConfig(min_messages=4, max_messages=6, preserve_first=False, on_prune=[hook]))
    p = make(reducer=reducer, messages_key="messages")
    fid = str(uuid.uuid4())
    p.save_state(fid, "step", {"id": fid, "memory_namespace": "/u", "messages": build_messages(2)})
    assert seen == []


def test_exactly_once_across_repeated_saves():
    seen, hook = _capture()
    reducer = MessageReducer(config=ReducerConfig(min_messages=4, max_messages=6, preserve_first=False, on_prune=[hook]))
    p = make(reducer=reducer, messages_key="messages")
    fid = str(uuid.uuid4())
    msgs = [dict(m, id=f"m{i}") for i, m in enumerate(build_messages(5))]
    p.save_state(fid, "s1", {"id": fid, "memory_namespace": "/u", "messages": msgs})
    p.save_state(fid, "s2", {"id": fid, "memory_namespace": "/u", "messages": msgs})   # same list again
    assert len(seen) == 1
