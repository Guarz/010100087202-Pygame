"""Đăng ký / đăng nhập bằng email + mật khẩu.

Email chỉ được lưu làm tên đăng nhập: server KHÔNG gửi email xác nhận (tránh giới hạn gửi mail
"email rate limit exceeded" của Supabase Auth), nên không cần cấu hình SMTP.

- Mật khẩu băm bằng PBKDF2-SHA256 (thư viện chuẩn hashlib), mỗi tài khoản một salt riêng.
- Sau khi đăng nhập, server cấp token ký HMAC bằng SECRET_KEY; trình duyệt gửi lại qua header Authorization.
- Tài khoản admin được tạo/cập nhật lúc khởi động từ ADMIN_EMAIL + ADMIN_PASSWORD,
  nên không ai "giành" được tài khoản admin bằng cách đăng ký trước.
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
# ADMIN_USERNAME: tên biến cũ, vẫn đọc để cấu hình đã đặt trên Render không bị hỏng.
ADMIN_EMAIL = (os.environ.get("ADMIN_EMAIL") or os.environ.get("ADMIN_USERNAME", "")).strip().lower()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

TOKEN_LIFETIME = 7 * 24 * 3600
PBKDF2_ROUNDS = 200_000
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_FAILURES, FAILURE_WINDOW = 8, 300

_failures = {}  # email -> [thời điểm đăng nhập sai gần đây]


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

def normalize_email(email):
    value = email.strip().lower()
    if len(value) > 254 or not EMAIL_RE.match(value):
        raise HTTPException(422, "Email không hợp lệ.")
    return value


def check_new_password(password, confirm):
    if len(password) < 6:
        raise HTTPException(422, "Mật khẩu phải có ít nhất 6 ký tự.")
    if password != confirm:
        raise HTTPException(422, "Mật khẩu xác nhận không khớp.")


def register(email, password, confirm):
    email = normalize_email(email)
    check_new_password(password, confirm)
    with engine.begin() as conn:
        if conn.execute(select(profiles.c.id).where(profiles.c.email == email)).first():
            raise HTTPException(409, "Email này đã được đăng ký.")
        user_id = uuid.uuid4().hex
        conn.execute(profiles.insert().values(id=user_id, email=email, password_hash=hash_password(password),
                                              display_name=email.split("@")[0][:40], role="player", banned=False))
        conn.execute(events.insert().values(user_id=user_id, type="register"))
    return make_token(user_id)


def login(email, password):
    # Không bắt buộc đúng định dạng email: tài khoản tạo trước đây đăng nhập bằng tên (vd "anh") vẫn vào được.
    name = email.strip().lower()
    now = time.time()
    recent = [t for t in _failures.get(name, []) if now - t < FAILURE_WINDOW]
    if len(recent) >= MAX_FAILURES:
        raise HTTPException(429, "Đăng nhập sai quá nhiều lần. Hãy thử lại sau 5 phút.")
    with engine.connect() as conn:
        row = conn.execute(select(profiles.c.id, profiles.c.password_hash, profiles.c.banned)
                           .where(profiles.c.email == name)).first()
    if row is None or not check_password(password, row.password_hash):
        _failures[name] = recent + [now]
        raise HTTPException(401, "Email hoặc mật khẩu không đúng.")
    if row.banned:
        raise HTTPException(403, "Tài khoản của bạn đã bị khóa bởi quản trị viên.")
    _failures.pop(name, None)
    return make_token(row.id)


def ensure_admin():
    """Tạo (hoặc đặt lại mật khẩu và quyền) cho tài khoản admin khai báo trong biến môi trường."""
    if not (ADMIN_EMAIL and ADMIN_PASSWORD):
        return
    with engine.begin() as conn:
        row = conn.execute(select(profiles.c.id, profiles.c.password_hash)
                           .where(profiles.c.email == ADMIN_EMAIL)).first()
        if row is None:
            conn.execute(profiles.insert().values(
                id=uuid.uuid4().hex, email=ADMIN_EMAIL, password_hash=hash_password(ADMIN_PASSWORD),
                display_name=ADMIN_EMAIL.split("@")[0][:40], role="admin", banned=False))
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
