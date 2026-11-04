import os

os.environ["DATABASE_URL"] = "sqlite:///./test_api.db"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["ADMIN_EMAIL"] = "thaygiao@truong.edu.vn"
os.environ["ADMIN_PASSWORD"] = "admin-test-pass"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import auth, main  # noqa: E402
from app.db import engine, metadata  # noqa: E402
from app.main import _last_judge, app  # noqa: E402
from tests.test_judge import SOLUTIONS  # noqa: E402


def bearer(token):
    return {"Authorization": "Bearer " + token}


@pytest.fixture()
def client():
    metadata.drop_all(engine)
    metadata.create_all(engine)
    auth._failures.clear()
    with TestClient(app) as c:
        reg = c.post("/api/auth/register", json={"email": "HocSinh@Test.vn", "password": "matkhau1", "password_confirm": "matkhau1"})
        assert reg.status_code == 200, reg.text
        c.player = bearer(reg.json()["token"])
        login = c.post("/api/auth/login", json={"email": "thaygiao@truong.edu.vn", "password": "admin-test-pass"})
        assert login.status_code == 200, login.text
        c.admin = bearer(login.json()["token"])
        yield c
    _last_judge.clear()


def submit(client, level_id, code, headers=None):
    _last_judge.clear()
    return client.post(f"/api/levels/{level_id}/submit", json={"code": code}, headers=headers or client.player)


def test_requires_login(client):
    assert client.get("/api/levels").status_code == 401
    assert client.get("/api/levels", headers=bearer("gia.mao")).status_code == 401
    forged = auth._b64(b'{"sub": "x", "exp": 9999999999}') + ".abc"
    assert client.get("/api/me", headers=bearer(forged)).status_code == 401


def test_static_files_are_revalidated(client):
    # Tránh trình duyệt giữ app.js cũ sau khi deploy bản mới.
    for path in ("/index.html", "/js/app.js", "/css/style.css"):
        res = client.get(path)
        assert res.status_code == 200 and res.headers["cache-control"] == "no-cache", path
        assert client.get(path, headers={"If-None-Match": res.headers["etag"]}).status_code == 304


def test_register_validation(client):
    def reg(email, password="matkhau1", confirm="matkhau1"):
        return client.post("/api/auth/register", json={"email": email, "password": password, "password_confirm": confirm})

    assert reg("hocsinh@test.vn").json()["detail"] == "Email này đã được đăng ký."  # không phân biệt hoa thường
    assert reg("khong-phai-email").status_code == 422
    assert reg("thieu@tenmien").status_code == 422
    assert reg("ban@moi.vn", confirm="khac123").json()["detail"] == "Mật khẩu xác nhận không khớp."
    assert reg("ban@moi.vn", password="123", confirm="123").status_code == 422
    assert reg("ban@moi.vn").status_code == 200


def test_login_checks_password_and_limits_guessing(client):
    me = client.get("/api/me", headers=client.player).json()
    assert me["email"] == "hocsinh@test.vn" and me["display_name"] == "hocsinh" and me["role"] == "player"
    for _ in range(auth.MAX_FAILURES):
        assert client.post("/api/auth/login", json={"email": "hocsinh@test.vn", "password": "sai"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "hocsinh@test.vn", "password": "matkhau1"}).status_code == 429


def test_passwords_are_hashed(client):
    with engine.connect() as conn:
        stored = conn.exec_driver_sql("SELECT password_hash FROM pq_profiles WHERE email = 'hocsinh@test.vn'").scalar()
    assert "matkhau1" not in stored and auth.check_password("matkhau1", stored)
    assert not auth.check_password("matkhau2", stored)


def test_all_levels_unlocked_by_default(client):
    levels = client.get("/api/levels", headers=client.player).json()["levels"]
    assert all(lv["unlocked"] for lv in levels)
    assert client.get("/api/levels/12", headers=client.player).status_code == 200


def test_levels_unlock_in_order_and_hidden_tests_stay_secret(client, monkeypatch):
    monkeypatch.setattr(main, "UNLOCK_ALL_LEVELS", False)
    levels = client.get("/api/levels", headers=client.player).json()["levels"]
    assert [lv["unlocked"] for lv in levels[:2]] == [True, False]
    assert client.get("/api/levels/2", headers=client.player).status_code == 403

    data = client.get("/api/levels/4", headers=client.admin).json()
    assert "tests" not in data and data["hidden_count"] == 2 and data["hints"] == []

    res = submit(client, 1, SOLUTIONS[1]).json()
    assert res["status"] == "passed" and res["score"] == 100 and res["new_item"]["id"] == "boots"
    assert client.get("/api/levels/2", headers=client.player).status_code == 200


def test_hints_reduce_score_and_progress_is_saved(client):
    submit(client, 1, SOLUTIONS[1])
    hint = client.post("/api/levels/2/hint", headers=client.player).json()
    assert hint["hints_used"] == 1 and len(hint["hints"]) == 1
    res = submit(client, 2, SOLUTIONS[2]).json()
    assert res["score"] == 90
    me = client.get("/api/me", headers=client.player).json()
    assert me["score"] == 190 and me["completed"] == 2 and me["rank"] == 1
    assert [i["id"] for i in client.get("/api/inventory", headers=client.player).json()] == ["boots", "gold_key"]
    assert client.get("/api/leaderboard").json()[0]["score"] == 190


def test_run_only_uses_visible_tests(client):
    res = client.post("/api/levels/1/run", json={"code": "move()"}, headers=client.player).json()
    assert res["total"] == 1 and res["animation"]["type"] == "robot" and res["animation"]["trace"] == ["move"]


def test_admin_only_endpoints(client):
    assert client.get("/api/admin/users", headers=client.player).status_code == 403
    users = client.get("/api/admin/users", headers=client.admin).json()
    player = next(u for u in users if u["email"] == "hocsinh@test.vn")
    assert client.patch(f"/api/admin/users/{player['id']}", json={"banned": True}, headers=client.admin).status_code == 200
    assert client.get("/api/me", headers=client.player).status_code == 403
    assert client.post("/api/auth/login", json={"email": "hocsinh@test.vn", "password": "matkhau1"}).status_code == 403
    res = client.patch(f"/api/admin/users/{player['id']}", json={"display_name": "  Học   Sinh  "}, headers=client.admin)
    assert res.json()["display_name"] == "Học Sinh"
    assert client.patch("/api/me", json={"display_name": "Hack"}, headers=client.player).status_code == 405
    admin_id = next(u["id"] for u in users if u["email"] == "thaygiao@truong.edu.vn")
    assert client.patch(f"/api/admin/users/{admin_id}", json={"display_name": "Thầy Giáo"}, headers=client.admin).status_code == 200
    assert client.patch(f"/api/admin/users/{admin_id}", json={"role": "player"}, headers=client.admin).status_code == 400
    stats = client.get("/api/admin/stats", headers=client.admin).json()
    assert stats["total_users"] == 2 and len(stats["levels"]) == 12


def test_admin_account_is_restored_from_env(client):
    with engine.begin() as conn:
        conn.exec_driver_sql("UPDATE pq_profiles SET role = 'player', banned = 1 WHERE email = 'thaygiao@truong.edu.vn'")
    auth.ensure_admin()
    me = client.get("/api/me", headers=client.admin).json()
    assert me["role"] == "admin"


def test_old_username_schema_is_renamed_and_accounts_keep_working(client):
    from app.db import init_db
    # Giả lập DB của bản trước: cột username, tài khoản "anh" tạo bằng tên chứ không phải email.
    with engine.begin() as conn:
        conn.exec_driver_sql("ALTER TABLE pq_profiles RENAME COLUMN email TO username")
        conn.exec_driver_sql("UPDATE pq_profiles SET username = 'anh' WHERE username = 'hocsinh@test.vn'")
    init_db()
    res = client.post("/api/auth/login", json={"email": "anh", "password": "matkhau1"})
    assert res.status_code == 200
    assert client.get("/api/me", headers=bearer(res.json()["token"])).json()["email"] == "anh"
