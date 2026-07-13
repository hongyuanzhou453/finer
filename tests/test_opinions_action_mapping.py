"""Pin the opinions-route ActionType mapping.

`_convert_action_step` falls back to "watch" for unmapped enum values, which
silently downgrades new action types in the UI. These tests fail loudly if a
schema ActionType is added without a mapping decision here.
"""
from __future__ import annotations

import pytest

from finer.api.routes.opinions import _ACTION_TYPE_MAP, _convert_action_step
from finer.schemas.trade_action import ActionStep as SchemaActionStep
from finer.schemas.trade_action import ActionType


def _step(action_type: ActionType, **kwargs) -> SchemaActionStep:
    return SchemaActionStep(sequence=1, action_type=action_type, **kwargs)


def test_every_schema_action_type_has_explicit_mapping():
    """No ActionType may rely on the silent "watch" fallback."""
    unmapped = [a.value for a in ActionType if a.value not in _ACTION_TYPE_MAP]
    assert unmapped == [], (
        f"ActionType values without an explicit opinions-route mapping "
        f"(would silently render as 'watch'): {unmapped}"
    )


@pytest.mark.parametrize(
    "action_type,expected",
    [
        (ActionType.LONG, "long"),
        (ActionType.SHORT, "short"),
        (ActionType.ADD, "add"),
        (ActionType.REDUCE, "reduce"),
        (ActionType.CLOSE_LONG, "close_long"),
        (ActionType.CLOSE_SHORT, "close_short"),
        (ActionType.HOLD, "watch"),
        (ActionType.WATCH, "watch"),
        (ActionType.BUY_AND_HOLD, "long"),
        (ActionType.BUY_CALL, "long"),
        (ActionType.SELL_CALL, "close_long"),
        (ActionType.BUY_PUT, "short"),
        (ActionType.SELL_PUT, "close_short"),
    ],
)
def test_action_type_mapping(action_type, expected):
    converted = _convert_action_step(_step(action_type))
    assert converted.actionType == expected


def test_position_delta_pct_passthrough():
    converted = _convert_action_step(
        _step(ActionType.REDUCE, position_delta_pct=-0.25)
    )
    assert converted.positionDeltaPct == -0.25

    no_delta = _convert_action_step(_step(ActionType.ADD))
    assert no_delta.positionDeltaPct is None
