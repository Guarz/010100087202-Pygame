"""Xác thực người dùng.

- AUTH_MODE=supabase (mặc định khi deploy): trình duyệt đăng nhập bằng Supabase Auth và gửi access token;
  server hỏi lại Supabase `/auth/v1/user` để xác minh token (hỗ trợ cả khóa ký JWT cũ lẫn mới).
- AUTH_MODE=dev: chỉ để chạy local, token có dạng "dev:<email>". Không bao giờ bật khi deploy.
"""
import os
import time

import httpx
from fastapi import Depends, Header, HTTPException
from sqlalchemy import func, select, update

from .db import engine, events, profiles

AUTH_MODE = os.environ.get("AUTH_MODE", "supabase")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
if AUTH_MODE not in ("dev", "supabase") or (AUTH_MODE == "supabase" and not (SUPABASE_URL and SUPABASE_ANON_KEY)):
    raise RuntimeError("Cần đặt SUPABASE_URL và SUPABASE_ANON_KEY (hoặc AUTH_MODE=dev khi chạy local).")
ADMIN_EMAILS = {e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()}

_token_cache = {}  # token -> (hết hạn, {"id", "email"})


async def _verify_supabase(token):
    cached = _token_cache.get(token)
    if cached and cached[0] > time.time():
        return cached[1]
    async with httpx.AsyncClient(timeout=8) as client:
        resp = await client.get(f"{SUPABASE_URL}/auth/v1/user",
                                headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {token}"})
    if resp.status_code != 200:
        raise HTTPException(401, "Phiên đăng nhập không hợp lệ hoặc đã hết hạn. Hãy đăng nhập lại.")
    data = resp.json()
    user = {"id": data["id"], "email": data.get("email") or "", "name": (data.get("user_metadata") or {}).get("display_name")}
    if len(_token_cache) > 5000:
        _token_cache.clear()
    _token_cache[token] = (time.time() + 60, user)
    return user


def _verify_dev(token):
    if not token.startswith("dev:") or "@" not in token:
        raise HTTPException(401, "Token dev không hợp lệ.")
    email = token[4:].strip().lower()[:200]
    return {"id": "dev-" + email, "email": email, "name": None}


def _ensure_profile(user):
    is_admin = user["email"].lower() in ADMIN_EMAILS
    with engine.begin() as conn:
        row = conn.execute(select(profiles).where(profiles.c.id == user["id"])).mappings().first()
        if row is None:
            name = (user.get("name") or user["email"].split("@")[0])[:40]
            conn.execute(profiles.insert().values(id=user["id"], email=user["email"], display_name=name,
                                                  role="admin" if is_admin else "player", banned=False))
            conn.execute(events.insert().values(user_id=user["id"], type="register"))
            row = conn.execute(select(profiles).where(profiles.c.id == user["id"])).mappings().first()
        else:
            changes = {"last_seen": func.now()}
            if is_admin and row["role"] != "admin":
                changes["role"] = "admin"
            conn.execute(update(profiles).where(profiles.c.id == user["id"]).values(**changes))
            row = {**row, **{k: v for k, v in changes.items() if k == "role"}}
    return dict(row)


async def current_user(authorization: str = Header(default="")):
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(401, "Bạn cần đăng nhập.")
    user = _verify_dev(token) if AUTH_MODE == "dev" else await _verify_supabase(token)
    profile = _ensure_profile(user)
    if profile["banned"]:
        raise HTTPException(403, "Tài khoản của bạn đã bị khóa bởi quản trị viên.")
    return profile


async def admin_user(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Chỉ quản trị viên mới truy cập được.")
    return user
