import pytest
from fastapi import HTTPException
from starlette.requests import Request
from test_team_bridge import login

from gateway_app.main import internal_session


def req(token, key):
    return Request(
        {
            "type": "http",
            "headers": [
                (b"authorization", ("Bearer " + token).encode()),
                (b"x-gateway-key", key.encode()),
            ],
        }
    )


def test_internal_api_checks_both_service_key_and_session(bridge):
    token, session, _ = login(bridge)
    key = bridge.team.settings.gateway_service_key.get_secret_value()
    assert internal_session(bridge.team, req(token, key)) is session
    with pytest.raises(HTTPException) as error:
        internal_session(bridge.team, req(token, "wrong"))
    assert error.value.status_code == 403
    with pytest.raises(HTTPException):
        internal_session(bridge.team, req("wrong", key))


def test_profile_is_owned_by_java_not_gateway_state(bridge):
    _, session, _ = login(bridge)
    bridge.team.state.put(
        session.account["id"], "profileMeta", {"confirmed": True, "pregnant": True}
    )
    bridge.profile.update(confirmed=False, pregnant=False)
    profile = bridge.team.profile(session)
    assert profile["confirmed"] is False and profile["pregnant"] is False


def test_snapshot_matches_rag_contract(bridge):
    pytest.importorskip("rag_app.meal_models")
    from rag_app.meal_models import MealSnapshot

    _, session, _ = login(bridge)
    value = MealSnapshot.model_validate(bridge.team.snapshot(session, "7"))
    assert value.plan.totals.energy_kcal == 200
    assert value.data_mode == "http"
