"""Flow state with non-JSON values (datetime, set, tuple, nested BaseModel, Decimal) must round-trip."""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from pydantic import BaseModel

from test_persistence import make as MAKE, build_messages


class Inner(BaseModel):
    when: datetime
    tags: set[str]


class State(BaseModel):
    id: str
    inner: Inner
    coords: tuple[float, float]
    amount: Decimal
    messages: list = []


def test_non_primitive_state_round_trips():
    p = MAKE()
    fid = str(uuid.uuid4())
    when = datetime(2026, 9, 20, 12, 30, tzinfo=timezone.utc)
    p.save_state(fid, "step", State(id=fid, inner=Inner(when=when, tags={"a", "b"}), coords=(1.5, 2.5),
                                    amount=Decimal("12.50"), messages=build_messages(1)))
    loaded = p.load_state(fid)
    assert loaded["inner"]["when"].startswith("2026-09-20T12:30:00")
    assert sorted(loaded["inner"]["tags"]) == ["a", "b"]
    assert list(loaded["coords"]) == [1.5, 2.5]
    assert float(loaded["amount"]) == 12.5


def test_non_primitive_dict_state_round_trips():
    p = MAKE()
    fid = str(uuid.uuid4())
    p.save_state(fid, "step", {"id": fid, "when": datetime(2026, 1, 1), "s": {1, 2}, "t": (1, 2), "n": Inner(when=datetime(2026, 1, 2), tags=set())})
    loaded = p.load_state(fid)
    assert loaded["when"].startswith("2026-01-01") and sorted(loaded["s"]) == [1, 2] and list(loaded["t"]) == [1, 2]
    assert loaded["n"]["when"].startswith("2026-01-02")
