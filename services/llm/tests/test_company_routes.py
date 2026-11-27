"""The dashboard API: characters, history, requests and team, through the real HTTP layer."""

import asyncio
from datetime import date, timedelta

import pytest

from company.characters import archive_inactive

TODAY = date(2026, 11, 27)  # a Friday; matches conftest.COMPANY_TODAY
MONDAY = TODAY + timedelta(days=10)  # 7 Dec 2026


@pytest.fixture
def as_user(make_token):
    def headers(user: str) -> dict:
        return {"Authorization": f"Bearer {make_token(user)}"}
    return headers


async def create(client, as_user, user="u-1", role="employee", name="Ada", dept=2):
    response = await client.post("/character", json={"displayName": name, "role": role, "departmentId": dept}, headers=as_user(user))
    assert response.status_code == 200, response.text
    return response.json()


def day_off(start=MONDAY, key="11111111-1111-1111-1111-111111111111", **extra):
    return {"kind": "day_off", "startsOn": start.isoformat(), "requestKey": key, **extra}


def scalar(conn, query, params=()):
    return conn.execute(query, params).fetchone()[0]


# --- characters ---------------------------------------------------------------------------------------


async def test_character_creation_flow_returns_the_character_and_me(company_client, as_user):
    assert (await company_client.get("/me", headers=as_user("u-1"))).json() is None
    made = await create(company_client, as_user, role="manager", name="Grace", dept=3)
    assert made["name"] == "Grace" and made["role"] == "manager" and made["department"] == "Engineering"
    me = (await company_client.get("/me", headers=as_user("u-1"))).json()
    assert me["employeeId"] == made["employeeId"] and me["title"] == "Engineering Manager"


async def test_double_post_character_yields_one_active_character(company_client, world_db, as_user):
    body = {"displayName": "Twin", "role": "manager", "departmentId": 3}
    first, second = await asyncio.gather(
        company_client.post("/character", json=body, headers=as_user("u-1")),
        company_client.post("/character", json=body, headers=as_user("u-1")))
    assert first.status_code == 200 and second.status_code == 200
    assert scalar(world_db, "SELECT count(*) FROM company.employees WHERE user_id = 'u-1' AND is_active") == 1
    mine = scalar(world_db, "SELECT id FROM company.employees WHERE user_id = 'u-1'")
    assert scalar(world_db, "SELECT count(*) FROM company.employees WHERE origin = 'simulated'") == scalar(
        world_db, "SELECT count(*) FROM company.employees WHERE manager_id = %s", (mine,))


@pytest.mark.parametrize(
    "raw,expected",
    [("  <b>Ada</b>   Lovelace ", "<b>Ada</b> Lovelace"), ("x" * 10_000, "x" * 60), ("Zoë 🚀", "Zoë 🚀")],
)
async def test_display_name_is_cleaned(company_client, as_user, raw, expected):
    assert (await create(company_client, as_user, name=raw))["name"] == expected


@pytest.mark.parametrize("body", [
    {"displayName": "   ", "role": "employee"},
    {"displayName": "Ok", "role": "superuser"},
    {"displayName": "Ok", "role": "employee", "departmentId": 999},
])
async def test_bad_character_requests_are_422(company_client, as_user, body):
    assert (await company_client.post("/character", json=body, headers=as_user("u-1"))).status_code == 422


async def test_changing_character_resets_the_history(company_client, world_db, as_user):
    first = await create(company_client, as_user, role="employee")
    second = await create(company_client, as_user, role="hr", dept=None)
    assert second["employeeId"] != first["employeeId"]
    assert scalar(world_db, "SELECT count(*) FROM company.employees WHERE user_id = 'u-1'") == 1


async def test_unauthenticated_calls_are_401(company_client):
    for method, path in (("get", "/me"), ("get", "/me/history"), ("post", "/character"), ("get", "/team")):
        assert (await getattr(company_client, method)(path)).status_code == 401


# --- history and requests ---------------------------------------------------------------------------------


async def test_endpoints_that_need_a_character_say_so(company_client, as_user):
    for path in ("/me/history", "/me/requests", "/team"):
        response = await company_client.get(path, headers=as_user("u-new"))
        assert response.status_code == 409 and "character" in response.json()["detail"].lower()


async def test_history_has_events_balance_and_recent_work_days(company_client, as_user):
    await create(company_client, as_user)
    history = (await company_client.get("/me/history", headers=as_user("u-1"))).json()
    assert history["today"] == TODAY.isoformat()
    assert any(e["kind"] == "hired" for e in history["events"])
    assert history["balance"]["year"] == 2026 and history["balance"]["allowance"] == 20
    assert history["balance"]["remaining"] == history["balance"]["allowance"] - history["balance"]["used"]
    assert 0 < len(history["recentWorkDays"]) <= 30


async def test_request_is_decided_in_the_same_call(company_client, as_user):
    await create(company_client, as_user)
    before = (await company_client.get("/me/history", headers=as_user("u-1"))).json()["balance"]["remaining"]
    response = await company_client.post("/me/requests", json=day_off(), headers=as_user("u-1"))
    body = response.json()
    assert response.status_code == 200 and body["status"] == "approved"
    assert body["decisionReason"].startswith("Approved") and body["balanceAfter"] == before - 1
    listed = (await company_client.get("/me/requests", headers=as_user("u-1"))).json()
    assert listed[0]["id"] == body["id"] and listed[0]["status"] == "approved"


async def test_a_refused_request_is_a_normal_answer_with_a_reason(company_client, as_user):
    await create(company_client, as_user)
    response = await company_client.post("/me/requests", json=day_off(start=date(2026, 12, 5), key="22222222-2222-2222-2222-222222222222"), headers=as_user("u-1"))  # Saturday
    assert response.status_code == 200 and response.json()["status"] == "rejected"
    assert "working day" in response.json()["decisionReason"]


@pytest.mark.parametrize("body", [
    {"kind": "day_off", "startsOn": "2026-12-10", "endsOn": "2026-12-07"},
    {"kind": "day_off", "startsOn": "9999-01-01"},
    {"kind": "day_off", "startsOn": "2026-12-07", "endsOn": "2036-12-07"},
    {"kind": "day_off", "startsOn": "1900-01-01"},
])
async def test_invalid_ranges_return_422_not_500(company_client, as_user, body):
    await create(company_client, as_user)
    response = await company_client.post("/me/requests", json={**body, "requestKey": "33333333-3333-3333-3333-333333333333"}, headers=as_user("u-1"))
    assert response.status_code == 422 and response.json()["detail"]


async def test_unparseable_dates_and_unknown_kinds_are_422(company_client, as_user):
    await create(company_client, as_user)
    for body in ({"kind": "day_off", "startsOn": "2026-13-45"}, {"kind": "holiday", "startsOn": "2026-12-07"}, {"kind": "day_off"}):
        assert (await company_client.post("/me/requests", json={**body, "requestKey": "44444444-4444-4444-4444-444444444444"}, headers=as_user("u-1"))).status_code == 422


async def test_21st_request_in_an_hour_is_429(company_client, as_user):
    await create(company_client, as_user)
    codes = []
    for i in range(21):
        key = f"00000000-0000-0000-0000-{i:012d}"
        response = await company_client.post("/me/requests", json={"kind": "remote_day", "startsOn": (MONDAY + timedelta(days=7 * i)).isoformat(), "requestKey": key}, headers=as_user("u-1"))
        codes.append(response.status_code)
    assert codes[:20] == [200] * 20 and codes[20] == 429


async def test_cancel_restores_the_balance(company_client, as_user):
    await create(company_client, as_user)
    start = (await company_client.get("/me/history", headers=as_user("u-1"))).json()["balance"]
    approved = (await company_client.post("/me/requests", json=day_off(), headers=as_user("u-1"))).json()
    cancelled = await company_client.post(f"/me/requests/{approved['id']}/cancel", headers=as_user("u-1"))
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    assert (await company_client.get("/me/history", headers=as_user("u-1"))).json()["balance"] == start


async def test_cancelling_a_missing_request_is_404(company_client, as_user):
    await create(company_client, as_user)
    assert (await company_client.post("/me/requests/999999/cancel", headers=as_user("u-1"))).status_code == 404


async def test_users_only_ever_see_and_change_their_own_requests(company_client, world_db, as_user):
    a = await create(company_client, as_user, user="u-a", name="Alice")
    b = await create(company_client, as_user, user="u-b", name="Bob")
    mine = (await company_client.post("/me/requests", json=day_off(employeeId=b["employeeId"]), headers=as_user("u-a"))).json()
    assert scalar(world_db, "SELECT employee_id FROM company.employee_requests WHERE id = %s", (mine["id"],)) == a["employeeId"]  # a forged employeeId is ignored
    theirs = (await company_client.get("/me/requests", headers=as_user("u-b"))).json()
    assert mine["id"] not in {r["id"] for r in theirs}  # Alice's new request is invisible to Bob
    owners = {scalar(world_db, "SELECT employee_id FROM company.employee_requests WHERE id = %s", (r["id"],)) for r in theirs}
    assert owners == {b["employeeId"]}  # everything Bob sees is Bob's own
    assert (await company_client.post(f"/me/requests/{mine['id']}/cancel", headers=as_user("u-b"))).status_code == 404


# --- team ---------------------------------------------------------------------------------------------------


async def test_team_is_manager_only(company_client, as_user):
    await create(company_client, as_user, user="u-emp", role="employee")
    assert (await company_client.get("/team", headers=as_user("u-emp"))).status_code == 403
    await create(company_client, as_user, user="u-mgr", role="manager", dept=3)
    team = (await company_client.get("/team", headers=as_user("u-mgr"))).json()
    assert 3 <= len(team) <= 5
    assert {"id", "name", "title", "todayStatus", "nextAway"} <= set(team[0])


# --- archived characters and activity ----------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/me", "/me/history", "/me/requests"])
async def test_archived_user_is_reactivated_by_any_call(company_client, world_db, generator_conn, as_user, path):
    made = await create(company_client, as_user, role="manager", dept=3)
    world_db.execute("UPDATE company.employees SET last_active_at = %s WHERE user_id = 'u-1'", (TODAY - timedelta(days=45),))
    assert archive_inactive(generator_conn, today=TODAY) == 1
    assert scalar(world_db, "SELECT is_active FROM company.employees WHERE user_id = 'u-1'") is False

    response = await company_client.get(path, headers=as_user("u-1"))

    assert response.status_code == 200
    assert scalar(world_db, "SELECT is_active FROM company.employees WHERE user_id = 'u-1'") is True
    assert (await company_client.get("/me", headers=as_user("u-1"))).json()["employeeId"] == made["employeeId"]


async def test_last_active_at_updates_at_most_hourly(company_client, world_db, as_user):
    await create(company_client, as_user)
    world_db.execute("UPDATE company.employees SET last_active_at = now() - interval '3 hours' WHERE user_id = 'u-1'")
    await company_client.get("/me", headers=as_user("u-1"))
    first = scalar(world_db, "SELECT last_active_at FROM company.employees WHERE user_id = 'u-1'")
    assert scalar(world_db, "SELECT now() - %s < interval '1 minute'", (first,)) is True
    await company_client.get("/me", headers=as_user("u-1"))
    await company_client.get("/me/history", headers=as_user("u-1"))
    assert scalar(world_db, "SELECT last_active_at FROM company.employees WHERE user_id = 'u-1'") == first


async def test_chat_reactivates_an_archived_character(company_client, company_app, world_db, generator_conn, as_user, monkeypatch):
    import core_llm.chat as chat_module

    async def fake_stream(*_args, **_kwargs):
        yield "data: ok\n\n"

    monkeypatch.setattr(chat_module, "stream_ui_messages", fake_stream)
    monkeypatch.setattr(chat_module, "company_today", lambda _settings: TODAY)
    company_app.state.graph = object()  # the route reads it before streaming; the fake stream ignores it
    await create(company_client, as_user)
    world_db.execute("UPDATE company.employees SET last_active_at = %s WHERE user_id = 'u-1'", (TODAY - timedelta(days=45),))
    archive_inactive(generator_conn, today=TODAY)
    body = {"id": "thread-1", "message": {"id": "m1", "role": "user", "parts": [{"type": "text", "text": "hello"}]}}
    response = await company_client.post("/chat", json=body, headers=as_user("u-1"))
    assert response.status_code == 200
    assert scalar(world_db, "SELECT is_active FROM company.employees WHERE user_id = 'u-1'") is True


# --- review fixes: concurrency and hostile input -------------------------------------------------------------


async def test_an_archived_users_page_load_in_parallel_has_no_errors(company_client, world_db, generator_conn, as_user):
    """The dashboard fires several calls at once; the first one reactivates, the rest must not collide with it."""
    for role in ("employee", "manager"):
        await create(company_client, as_user, role=role, dept=3)
        world_db.execute("UPDATE company.employees SET last_active_at = %s WHERE user_id = 'u-1'", (TODAY - timedelta(days=45),))
        assert archive_inactive(generator_conn, today=TODAY) == 1
        paths = ["/me", "/me/history", "/me/requests", "/me", "/me/history", "/me/requests"]
        responses = await asyncio.gather(*(company_client.get(p, headers=as_user("u-1")) for p in paths))
        assert [r.status_code for r in responses] == [200] * len(paths), [r.text[:120] for r in responses if r.status_code != 200]
        assert scalar(world_db, "SELECT count(*) FROM company.employees WHERE user_id = 'u-1' AND is_active") == 1


async def test_changing_character_while_other_calls_are_in_flight_never_errors(company_client, world_db, as_user):
    await create(company_client, as_user, role="employee", dept=3)
    for round_ in range(2):
        role = "manager" if round_ == 0 else "hr"
        calls = [
            company_client.post("/character", json={"displayName": "Switch", "role": role, "departmentId": 3 if role == "manager" else None}, headers=as_user("u-1")),
            company_client.post("/me/requests", json=day_off(start=MONDAY + timedelta(days=7 * round_), key=f"5555555{round_}-5555-5555-5555-555555555555"), headers=as_user("u-1")),
            company_client.get("/me/history", headers=as_user("u-1")),
            company_client.get("/me/requests", headers=as_user("u-1")),
            company_client.post("/me/requests/1/cancel", headers=as_user("u-1")),
        ]
        responses = await asyncio.gather(*calls)
        assert all(r.status_code < 500 for r in responses), [(r.status_code, r.text[:100]) for r in responses]
        assert scalar(world_db, "SELECT count(*) FROM company.employees WHERE user_id = 'u-1' AND is_active") == 1


@pytest.mark.parametrize("hours", ["NaN", "Infinity", "-1", "0", "0.001", "25"])
async def test_overtime_hours_must_be_a_sensible_number(company_client, as_user, hours):
    await create(company_client, as_user)
    raw = f'{{"kind": "overtime", "startsOn": "2026-12-07", "hours": {hours}, "requestKey": "66666666-6666-6666-6666-666666666666"}}'
    response = await company_client.post("/me/requests", content=raw, headers={**as_user("u-1"), "content-type": "application/json"})
    assert response.status_code == 422, response.text
