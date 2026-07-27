"""
E2E tests for DynamoDBFlowPersistence against real DynamoDB.

Requires AWS credentials (AWS_PROFILE / keys) + region. The table is
auto-created (PAY_PER_REQUEST, key = flow_uuid) on first use.
"""
import os
import uuid

import pytest
from pydantic import BaseModel

from crewai_persistence_dynamodb import DynamoDBFlowPersistence
from agentstate_reducer import MessageReducer
from agentstate_reducer.models import ReducerConfig

TABLE = os.environ.get("CREWAI_DDB_TABLE", "crewai_flows_test")


def make(**kwargs):
    return DynamoDBFlowPersistence(table_name=TABLE, **kwargs)


def build_messages(n_pairs):
    msgs = []
    for i in range(n_pairs):
        msgs.append({"role": "human", "content": f"msg {i}"})
        msgs.append({"role": "ai", "content": f"reply {i}"})
    return msgs


def test_save_and_load_dict_state():
    p = make()
    fid = str(uuid.uuid4())
    state = {"id": fid, "user": "kamal", "step": 3, "nested": {"a": 1}}
    p.save_state(fid, "my_step", state)
    loaded = p.load_state(fid)
    assert loaded is not None
    assert loaded["user"] == "kamal"
    assert loaded["step"] == 3
    assert loaded["nested"] == {"a": 1}


def test_save_and_load_pydantic_state():
    class MyState(BaseModel):
        id: str
        counter: int
        label: str

    p = make()
    fid = str(uuid.uuid4())
    p.save_state(fid, "step", MyState(id=fid, counter=7, label="hello"))
    loaded = p.load_state(fid)
    assert loaded["counter"] == 7
    assert loaded["label"] == "hello"


def test_load_missing_returns_none():
    assert make().load_state(str(uuid.uuid4())) is None


def test_latest_save_wins():
    p = make()
    fid = str(uuid.uuid4())
    p.save_state(fid, "s1", {"id": fid, "v": 1})
    p.save_state(fid, "s2", {"id": fid, "v": 2})
    assert p.load_state(fid)["v"] == 2


def test_no_reducer_keeps_all_messages():
    p = make()
    fid = str(uuid.uuid4())
    msgs = build_messages(10)  # 20 messages
    p.save_state(fid, "chat", {"id": fid, "messages": msgs})
    loaded = p.load_state(fid)
    assert len(loaded["messages"]) == 20
    assert loaded["messages"] == msgs


def test_reducer_caps_messages():
    reducer = MessageReducer(config=ReducerConfig(min_messages=4, max_messages=6))
    p = make(reducer=reducer, messages_key="messages")
    fid = str(uuid.uuid4())
    p.save_state(fid, "chat", {"id": fid, "messages": build_messages(10)})
    loaded = p.load_state(fid)
    # min_messages=4 + preserve_first allows up to 5
    assert len(loaded["messages"]) <= 5


def test_reducer_preserves_recent_tail():
    reducer = MessageReducer(config=ReducerConfig(min_messages=4, max_messages=6))
    p = make(reducer=reducer, messages_key="messages")
    fid = str(uuid.uuid4())
    msgs = build_messages(10)  # newest is {"role":"ai","content":"reply 9"}
    p.save_state(fid, "chat", {"id": fid, "messages": msgs})
    surviving = p.load_state(fid)["messages"]
    assert surviving[0] == msgs[0]                          # preserve_first
    assert surviving[-1] == {"role": "ai", "content": "reply 9"}  # most recent kept
