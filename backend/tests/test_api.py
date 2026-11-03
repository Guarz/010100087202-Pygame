import os

os.environ["AUTH_MODE"] = "dev"
os.environ["DATABASE_URL"] = "sqlite:///./test_api.db"
os.environ["ADMIN_EMAILS"] = "admin@test.vn"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import engine, metadata  # noqa: E402
from app.main import _last_judge, app  # noqa: E402
from tests.test_judge import SOLUTIONS  # noqa: E402

PLAYER = {"Authorization": "Bearer dev:hs@test.vn"}
ADMIN = {"Authorization": "Bearer dev:admin@test.vn"}


@pytest.fixture()
def client():
    metadata.drop_all(engine)
    metadata.create_all(engine)
    with TestClient(app) as c:
        yield c
    _last_judge.clear()


def submit(client, level_id, code, headers=PLAYER):
    _last_judge.clear()
    return client.post(f"/api/levels/{level_id}/submit", json={"code": code}, headers=headers)


def test_requires_login(client):
    assert client.get("/api/levels").status_code == 401


def test_levels_unlock_in_order_and_hidden_tests_stay_secret(client):
    levels = client.get("/api/levels", headers=PLAYER).json()["levels"]
    assert [lv["unlocked"] for lv in levels[:2]] == [True, False]
    assert client.get("/api/levels/2", headers=PLAYER).status_code == 403

    data = client.get("/api/levels/4", headers=ADMIN).json()
    assert "tests" not in data and data["hidden_count"] == 2 and data["hints"] == []

    res = submit(client, 1, SOLUTIONS[1]).json()
    assert res["status"] == "passed" and res["score"] == 100 and res["new_item"]["id"] == "boots"
    assert client.get("/api/levels/2", headers=PLAYER).status_code == 200


def test_hints_reduce_score_and_progress_is_saved(client):
    submit(client, 1, SOLUTIONS[1])
    hint = client.post("/api/levels/2/hint", headers=PLAYER).json()
    assert hint["hints_used"] == 1 and len(hint["hints"]) == 1
    res = submit(client, 2, SOLUTIONS[2]).json()
    assert res["score"] == 90
    me = client.get("/api/me", headers=PLAYER).json()
    assert me["score"] == 190 and me["completed"] == 2 and me["rank"] == 1
    assert [i["id"] for i in client.get("/api/inventory", headers=PLAYER).json()] == ["boots", "gold_key"]
    assert client.get("/api/leaderboard").json()[0]["score"] == 190


def test_run_only_uses_visible_tests(client):
    res = client.post("/api/levels/1/run", json={"code": "move()"}, headers=PLAYER).json()
    assert res["total"] == 1 and res["animation"]["type"] == "robot" and res["animation"]["trace"] == ["move"]


def test_admin_only_endpoints(client):
    client.get("/api/me", headers=PLAYER)
    assert client.get("/api/admin/users", headers=PLAYER).status_code == 403
    users = client.get("/api/admin/users", headers=ADMIN).json()
    player = next(u for u in users if u["email"] == "hs@test.vn")
    assert client.patch(f"/api/admin/users/{player['id']}", json={"banned": True}, headers=ADMIN).status_code == 200
    assert client.get("/api/me", headers=PLAYER).status_code == 403
    res = client.patch(f"/api/admin/users/{player['id']}", json={"display_name": "  Học   Sinh  "}, headers=ADMIN)
    assert res.json()["display_name"] == "Học Sinh"
    assert client.patch("/api/me", json={"display_name": "Hack"}, headers=PLAYER).status_code == 405
    admin_id = next(u["id"] for u in users if u["email"] == "admin@test.vn")
    assert client.patch(f"/api/admin/users/{admin_id}", json={"display_name": "Thầy Giáo"}, headers=ADMIN).status_code == 200
    assert client.patch(f"/api/admin/users/{admin_id}", json={"role": "player"}, headers=ADMIN).status_code == 400
    stats = client.get("/api/admin/stats", headers=ADMIN).json()
    assert stats["total_users"] == 2 and len(stats["levels"]) == 12
