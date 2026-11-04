"""Đăng ký / đăng nhập bằng tên đăng nhập + mật khẩu (không cần email).

- Mật khẩu băm bằng PBKDF2-SHA256 (thư viện chuẩn hashlib), mỗi tài khoản một salt riêng.
- Sau khi đăng nhập, server cấp token ký HMAC bằng SECRET_KEY; trình duyệt gửi lại qua header Authorization.
- Tài khoản admin được tạo/cập nhật lúc khởi động từ ADMIN_USERNAME + ADMIN_PASSWORD,
  nên không ai "giành" được tên admin bằng cách đăng ký trước.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import time
import uuid

from fastapi import Depends, Header, HTTPException
from sqlalchemy import func, select, update

from .db import engine, events, profiles

SECRET_KEY = os.environ.get("SECRET_KEY", "")
if not SECRET_KEY:
    # Chạy local không cấu hình: dùng khóa ngẫu nhiên (token mất hiệu lực mỗi lần khởi động lại server).
    SECRET_KEY = secrets.token_hex(32)
    print("CẢNH BÁO: chưa đặt SECRET_KEY, dùng khóa tạm thời.", file=sys.stderr)
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "").strip().lower()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

TOKEN_LIFETIME = 7 * 24 * 3600
PBKDF2_ROUNDS = 200_000
USERNAME_RE = re.compile(r"^[a-z0-9_]{3,20}$")
MAX_FAILURES, FAILURE_WINDOW = 8, 300

_failures = {}  # username -> [thời điểm đăng nhập sai gần đây]


# ------------------------------------------------------------------ mật khẩu & token

def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${_b64(salt)}${_b64(digest)}"


def check_password(password, stored):
    try:
        _, rounds, salt, digest = stored.split("$")
        got = hashlib.pbkdf2_hmac("sha256", password.encode(), _unb64(salt), int(rounds))
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(got, _unb64(digest))


def make_token(user_id):
    body = _b64(json.dumps({"sub": user_id, "exp": int(time.time()) + TOKEN_LIFETIME}).encode())
    return body + "." + _sign(body)


def read_token(token):
    try:
        body, sig = token.split(".")
        if not hmac.compare_digest(sig, _sign(body)):
            return None
        data = json.loads(_unb64(body))
    except ValueError:
        return None
    return data["sub"] if data.get("exp", 0) > time.time() else None


def _sign(body):
    return _b64(hmac.new(SECRET_KEY.encode(), body.encode(), hashlib.sha256).digest())


def _b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# ------------------------------------------------------------------ tài khoản

def normalize_username(username):
    name = username.strip().lower()
    if not USERNAME_RE.match(name):
        raise HTTPException(422, "Tên đăng nhập gồm 3–20 ký tự: chữ không dấu, số hoặc dấu gạch dưới (_).")
    return name


def check_new_password(password, confirm):
    if len(password) < 6:
        raise HTTPException(422, "Mật khẩu phải có ít nhất 6 ký tự.")
    if password != confirm:
        raise HTTPException(422, "Mật khẩu xác nhận không khớp.")


def register(username, password, confirm):
    name = normalize_username(username)
    check_new_password(password, confirm)
    with engine.begin() as conn:
        if conn.execute(select(profiles.c.id).where(profiles.c.username == name)).first():
            raise HTTPException(409, "Tên đăng nhập này đã có người dùng.")
        user_id = uuid.uuid4().hex
        conn.execute(profiles.insert().values(id=user_id, username=name, password_hash=hash_password(password),
                                              display_name=name, role="player", banned=False))
        conn.execute(events.insert().values(user_id=user_id, type="register"))
    return make_token(user_id)


def login(username, password):
    name = username.strip().lower()
    now = time.time()
    recent = [t for t in _failures.get(name, []) if now - t < FAILURE_WINDOW]
    if len(recent) >= MAX_FAILURES:
        raise HTTPException(429, "Đăng nhập sai quá nhiều lần. Hãy thử lại sau 5 phút.")
    with engine.connect() as conn:
        row = conn.execute(select(profiles.c.id, profiles.c.password_hash, profiles.c.banned)
                           .where(profiles.c.username == name)).first()
    if row is None or not check_password(password, row.password_hash):
        _failures[name] = recent + [now]
        raise HTTPException(401, "Tên đăng nhập hoặc mật khẩu không đúng.")
    if row.banned:
        raise HTTPException(403, "Tài khoản của bạn đã bị khóa bởi quản trị viên.")
    _failures.pop(name, None)
    return make_token(row.id)


def ensure_admin():
    """Tạo (hoặc đặt lại mật khẩu và quyền) cho tài khoản admin khai báo trong biến môi trường."""
    if not (ADMIN_USERNAME and ADMIN_PASSWORD):
        return
    if not USERNAME_RE.match(ADMIN_USERNAME):
        raise RuntimeError("ADMIN_USERNAME không hợp lệ (3–20 ký tự a-z, 0-9, _).")
    with engine.begin() as conn:
        row = conn.execute(select(profiles.c.id, profiles.c.password_hash)
                           .where(profiles.c.username == ADMIN_USERNAME)).first()
        if row is None:
            conn.execute(profiles.insert().values(
                id=uuid.uuid4().hex, username=ADMIN_USERNAME, password_hash=hash_password(ADMIN_PASSWORD),
                display_name=ADMIN_USERNAME, role="admin", banned=False))
        else:
            values = {"role": "admin", "banned": False}
            if not check_password(ADMIN_PASSWORD, row.password_hash):
                values["password_hash"] = hash_password(ADMIN_PASSWORD)
            conn.execute(update(profiles).where(profiles.c.id == row.id).values(**values))


# ------------------------------------------------------------------ dependency cho các route

async def current_user(authorization: str = Header(default="")):
    user_id = read_token(authorization.removeprefix("Bearer ").strip())
    if not user_id:
        raise HTTPException(401, "Bạn cần đăng nhập (hoặc phiên đăng nhập đã hết hạn).")
    with engine.begin() as conn:
        row = conn.execute(select(profiles).where(profiles.c.id == user_id)).mappings().first()
        if row is None:
            raise HTTPException(401, "Tài khoản không còn tồn tại.")
        conn.execute(update(profiles).where(profiles.c.id == user_id).values(last_seen=func.now()))
    if row["banned"]:
        raise HTTPException(403, "Tài khoản của bạn đã bị khóa bởi quản trị viên.")
    return dict(row)


async def admin_user(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Chỉ quản trị viên mới truy cập được.")
    return user
