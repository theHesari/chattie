"""JWT verification and thread ownership at the API boundary."""

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core_llm import threads


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_missing_token_is_401(client):
    assert (await client.get("/threads")).status_code == 401


async def test_valid_token_is_accepted(client, make_token):
    assert (await client.get("/threads", headers=bearer(make_token("user-a")))).status_code == 200


@pytest.mark.parametrize(
    "overrides",
    [{"exp_in": -60}, {"aud": "someone-else"}, {"iss": "https://evil.example"}],
    ids=["expired", "wrong-audience", "wrong-issuer"],
)
async def test_bad_claims_are_401(client, make_token, overrides):
    response = await client.get("/threads", headers=bearer(make_token("user-a", **overrides)))
    assert response.status_code == 401


async def test_token_signed_with_another_key_is_401(client, make_token):
    forged = make_token("user-a", key=Ed25519PrivateKey.generate())
    assert (await client.get("/threads", headers=bearer(forged))).status_code == 401


async def test_other_users_thread_is_404_on_read(client, api_app, make_token):
    await threads.touch(api_app.state.db_pool, "thread-1", "user-a", "hello")
    response = await client.get("/threads/thread-1/messages", headers=bearer(make_token("user-b")))
    assert response.status_code == 404


async def test_other_users_thread_is_404_on_chat(client, api_app, make_token):
    await threads.touch(api_app.state.db_pool, "thread-1", "user-a", "hello")
    body = {"id": "thread-1", "message": {"id": "m1", "role": "user", "parts": [{"type": "text", "text": "hi"}]}}
    response = await client.post("/chat", json=body, headers=bearer(make_token("user-b")))
    assert response.status_code == 404


async def test_nonexistent_and_foreign_threads_look_the_same(client, api_app, make_token):
    await threads.touch(api_app.state.db_pool, "thread-1", "user-a", "hello")
    body = {"id": "thread-1", "message": {"id": "m1", "role": "user", "parts": [{"type": "text", "text": "hi"}]}}
    foreign = await client.post("/chat", json=body, headers=bearer(make_token("user-b")))
    assert foreign.json() == {"detail": "thread not found"}


async def test_list_threads_returns_only_own(client, api_app, make_token):
    pool = api_app.state.db_pool
    await threads.touch(pool, "thread-a", "user-a", "mine")
    await threads.touch(pool, "thread-b", "user-b", "theirs")
    response = await client.get("/threads", headers=bearer(make_token("user-a")))
    assert [t["id"] for t in response.json()] == ["thread-a"]
