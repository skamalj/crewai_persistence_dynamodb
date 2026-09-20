"""Amazon DynamoDB persistence backend for CrewAI Flows.

Implements CrewAI's ``FlowPersistence`` (``init_db`` / ``save_state`` /
``load_state``) on DynamoDB. One item per flow, keyed by ``flow_uuid`` — each
save upserts the latest state, so ``load_state`` returns the most recent.

Flow state is stored as a JSON string in a ``data`` attribute, which sidesteps
DynamoDB's float/Decimal and empty-value quirks. Optionally prunes a message
list in the state via a ``MessageReducer`` (from ``agentstate-reducer``) before
each save.

Note: current CrewAI defines ``FlowPersistence`` as a Pydantic ``BaseModel``, so
configuration is declared as pydantic fields and runtime objects (the boto3
clients, the reducer) are held as private attributes.
"""

import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union

import boto3
from botocore.exceptions import ClientError
from pydantic import BaseModel, Field, PrivateAttr

from crewai.flow.persistence.base import FlowPersistence



def _memory_namespace(reducer: Any, state: Dict[str, Any], flow_uuid: str) -> str:
    """Resolve the long-term-memory namespace forwarded to reducer ``on_prune`` hooks.

    Looks up ``reducer.config.namespace_key`` (default ``"memory_namespace"``) in
    the flow state; the app sets it in its state model, e.g.
    ``memory_namespace = "/user/kamal"`` (a CrewAI Memory scope path). Falls back
    to ``"/flow/<flow_uuid>"`` so apps that never set it still get per-flow
    memory. The persistence layer never builds the namespace beyond that fallback.
    """
    key = getattr(getattr(reducer, "config", None), "namespace_key", "memory_namespace")
    ns = state.get(key)
    return ns if ns is not None else f"/flow/{flow_uuid}"


def _apply_reducer(reducer: Any, state: Dict[str, Any], messages_key: str, flow_uuid: str) -> None:
    """Prune ``state[messages_key]`` in place, forwarding the memory namespace.

    agentstate-reducer >= 0.4.0 accepts ``namespace=``; older reducers ignore it.
    """
    try:
        result = reducer.reduce(
            existing=state[messages_key], new=[], namespace=_memory_namespace(reducer, state, flow_uuid)
        )
    except TypeError:  # agentstate-reducer < 0.4.0
        result = reducer.reduce(existing=state[messages_key], new=[])
    state[messages_key] = result.surviving

class DynamoDBFlowPersistence(FlowPersistence):
    """DynamoDB-backed persistence for CrewAI Flows."""

    persistence_type: str = Field(default="DynamoDBFlowPersistence")
    table_name: str
    region_name: Optional[str] = None
    endpoint_url: Optional[str] = None
    ttl_seconds: Optional[int] = None
    messages_key: str = "messages"

    _reducer: Any = PrivateAttr(default=None)
    _boto_session: Any = PrivateAttr(default=None)
    _dynamodb: Any = PrivateAttr(default=None)
    _client: Any = PrivateAttr(default=None)
    _table: Any = PrivateAttr(default=None)

    def __init__(
        self,
        table_name: str,
        *,
        region_name: Optional[str] = None,
        boto_session: Optional["boto3.Session"] = None,
        endpoint_url: Optional[str] = None,
        ttl_seconds: Optional[int] = None,
        reducer: Any = None,
        messages_key: str = "messages",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            table_name=table_name,
            region_name=region_name,
            endpoint_url=endpoint_url,
            ttl_seconds=ttl_seconds,
            messages_key=messages_key,
            **kwargs,
        )
        self._reducer = reducer
        self._boto_session = boto_session
        self.init_db()

    def init_db(self) -> None:
        session = self._boto_session or boto3.Session(region_name=self.region_name)
        self._dynamodb = session.resource("dynamodb", endpoint_url=self.endpoint_url)
        self._client = session.client("dynamodb", endpoint_url=self.endpoint_url)

        table = self._dynamodb.Table(self.table_name)
        try:
            table.load()
            self._table = table
            return
        except ClientError as e:
            if e.response["Error"]["Code"] != "ResourceNotFoundException":
                raise
        table = self._dynamodb.create_table(
            TableName=self.table_name,
            KeySchema=[{"AttributeName": "flow_uuid", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "flow_uuid", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        table.wait_until_exists()
        if self.ttl_seconds:
            try:
                self._client.update_time_to_live(
                    TableName=self.table_name,
                    TimeToLiveSpecification={"Enabled": True, "AttributeName": "ttl"},
                )
            except ClientError:  # pragma: no cover - best effort
                pass
        self._table = table

    def save_state(
        self,
        flow_uuid: str,
        method_name: str,
        state_data: Union[Dict[str, Any], BaseModel],
    ) -> None:
        if isinstance(state_data, BaseModel):
            d: Dict[str, Any] = state_data.model_dump()
        else:
            d = dict(state_data)

        if self._reducer is not None and self.messages_key in d:
            _apply_reducer(self._reducer, d, self.messages_key, flow_uuid)

        item = {
            "flow_uuid": flow_uuid,
            "data": json.dumps(d),
            "method_name": method_name,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        if self.ttl_seconds:
            item["ttl"] = int(time.time()) + self.ttl_seconds
        self._table.put_item(Item=item)

    def load_state(self, flow_uuid: str) -> Optional[Dict[str, Any]]:
        resp = self._table.get_item(Key={"flow_uuid": flow_uuid}, ConsistentRead=True)
        item = resp.get("Item")
        if not item:
            return None
        return json.loads(item["data"])
