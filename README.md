# crewai-persistence-dynamodb

Amazon DynamoDB persistence backend for [CrewAI Flows](https://docs.crewai.com/concepts/flows). Persists flow state across runs, with optional built-in message pruning via [agentstate-reducer](https://pypi.org/project/agentstate-reducer/).

Implements CrewAI's `FlowPersistence` interface, so it drops straight into the `@persist` decorator.

## Installation

```bash
pip install crewai-persistence-dynamodb
# with message pruning:
pip install "crewai-persistence-dynamodb[reducer]"
```

**Requires Python 3.10–3.13** (matches CrewAI's supported range).

## Usage

```python
from crewai.flow.flow import Flow, start
from crewai.flow.persistence import persist
from crewai_persistence_dynamodb import DynamoDBFlowPersistence

backend = DynamoDBFlowPersistence(table_name="crewai-flows", region_name="us-east-1")

@persist(backend)
class MyFlow(Flow[MyState]):
    @start()
    def begin(self):
        self.state.counter += 1
```

The table is auto-created (on-demand billing) if it doesn't exist, keyed by `flow_uuid`.

### With message pruning (conversational flows)

```python
from agentstate_reducer import MessageReducer
from crewai_persistence_dynamodb import DynamoDBFlowPersistence

backend = DynamoDBFlowPersistence(
    table_name="crewai-flows",
    reducer=MessageReducer(min_messages=10, max_messages=20),
    messages_key="messages",   # state field holding the message list
)
```

## API

### `DynamoDBFlowPersistence(table_name, *, region_name=None, boto_session=None, endpoint_url=None, ttl_seconds=None, reducer=None, messages_key="messages")`

| Parameter | Description |
|---|---|
| `table_name` | DynamoDB table (auto-created if absent) |
| `region_name` | AWS region |
| `boto_session` | Optional pre-built `boto3.Session` |
| `endpoint_url` | Custom endpoint (DynamoDB Local / LocalStack) |
| `ttl_seconds` | If set, flow state expires automatically via a `ttl` attribute |
| `reducer` | Optional `MessageReducer` to prune `messages_key` before each save |
| `messages_key` | State field holding the message list (default `"messages"`) |

## Authentication

Standard boto3 credential resolution — env vars, `~/.aws/credentials`, `AWS_PROFILE`, SSO, or IAM roles. Needs permission to create the table (if absent) and read/write items.

## Data model

One item per flow, keyed by `flow_uuid`. The flow state is stored as a JSON string in a `data` attribute; `method_name` and `saved_at` are stored alongside as metadata. Each save upserts, so `load_state` returns the latest state.

## License

MIT
