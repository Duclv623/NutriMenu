"""Regression: DB timestamp/number/set serialization must not revoke confirmation."""

import copy

from test_team_bridge import login

from gateway_app.integration import UIProfile, revision


def test_profile_confirmation_survives_database_roundtrip(bridge):
    _, session, _ = login(bridge)
    saved = {
        **bridge.profile,
        "confirmed": True,
        "pregnant": True,
        "specialDiet": True,
        "version": 3,
        "updatedAt": "2026-11-21T12:00:00.123456789Z",
        "allergies": ["Trứng", "Sữa"],
        "height": 170,
    }
    bridge.team.state.put(
        session.account["id"],
        "profileMeta",
        {
            "revision": revision(saved),
            "confirmed": True,
            "pregnant": True,
            "specialDiet": True,
        },
    )
    reloaded = copy.deepcopy(saved)
    reloaded.update(
        updatedAt="2026-11-21T12:00:00.123457Z",
        height=170.0,
        allergies=["Sữa", "Trứng"],
    )
    result = bridge.team.profile(session, reloaded)
    assert result["confirmed"] is True
    assert result["pregnant"] is True and result["specialDiet"] is True
    assert set(result["allergies"]) == {"Trứng", "Sữa"}


def test_save_then_reload_reads_health_flags_from_user_service(bridge):
    _, session, _ = login(bridge)
    draft = UIProfile.model_validate(
        {
            **bridge.team.profile(session),
            "confirmed": True,
            "pregnant": True,
            "specialDiet": True,
            "allergies": ["Trứng"],
        }
    )
    saved = bridge.team.save_profile(session, draft)
    reloaded = bridge.team.profile(session)
    assert saved["version"] == reloaded["version"] == 2
    assert reloaded["confirmed"] and reloaded["pregnant"] and reloaded["specialDiet"]
    assert reloaded["allergies"] == ["Trứng"]
    assert not any(key == "profileMeta" for _, key in bridge.team.state.values)
