"""The API's real JSON, recorded for the web app's contract tests.

The web app validates every response with zod schemas (apps/web/lib/api/schemas.ts). Those schemas are
tested in Node against the files this test writes, so a backend change that breaks the contract fails
here first (the key assertions) and in `npm test` in apps/web second (the schemas against the fixtures).
Only volatile values (the wall-clock creation time of a new request) are pinned; everything else is the
server's real output.
"""

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[3] / "apps" / "web" / "lib" / "api" / "fixtures"
TODAY = date(2026, 11, 27)
MONDAY = TODAY + timedelta(days=10)
PINNED_CREATED_AT = "2026-11-27T12:00:00+00:00"


def write(name: str, payload) -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    (FIXTURES / f"{name}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


@pytest.fixture
def as_user(make_token):
    return lambda user: {"Authorization": f"Bearer {make_token(user)}"}


async def test_record_the_contract(company_client, as_user):
    me = as_user("u-contract")
    created = await company_client.post("/character", json={"displayName": "Ada Lovelace", "role": "manager", "departmentId": 2}, headers=me)
    assert created.status_code == 200
    character = created.json()
    assert set(character) == {"employeeId", "name", "title", "role", "department", "managerName"}

    filed = await company_client.post(
        "/me/requests", json={"kind": "day_off", "startsOn": MONDAY.isoformat(), "reason": "Long weekend",
                              "requestKey": "11111111-2222-3333-4444-555555555555"}, headers=me)
    assert filed.status_code == 200
    result = filed.json()
    assert set(result) == {"id", "status", "decisionReason", "balanceAfter"}

    history = (await company_client.get("/me/history", headers=me)).json()
    assert set(history) == {"today", "events", "balance", "recentWorkDays"}
    assert set(history["balance"]) == {"year", "allowance", "used", "remaining"}
    assert history["events"] and set(history["events"][0]) == {"happenedAt", "kind", "title", "details"}
    assert history["recentWorkDays"] and set(history["recentWorkDays"][0]) == {"day", "hours", "kind"}

    requests = (await company_client.get("/me/requests", headers=me)).json()
    assert requests and set(requests[0]) == {
        "id", "kind", "startsOn", "endsOn", "startTime", "endTime", "hours", "reason", "status", "decisionReason", "createdAt"}
    for row in requests:
        row["createdAt"] = PINNED_CREATED_AT  # the only wall-clock value in the fixtures

    team = (await company_client.get("/team", headers=me)).json()
    assert team and set(team[0]) == {"id", "name", "title", "todayStatus", "nextAway"}

    me_view = (await company_client.get("/me", headers=me)).json()
    assert me_view == character

    cancelled = (await company_client.post(f"/me/requests/{result['id']}/cancel", headers=me)).json()
    assert set(cancelled) == {"id", "status", "decisionReason", "balanceAfter"} and cancelled["status"] == "cancelled"

    for name, payload in (("character", me_view), ("history", history), ("requests", requests), ("result", result),
                          ("cancelled", cancelled), ("team", team)):
        write(name, payload)
