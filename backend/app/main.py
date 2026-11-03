"""Python Quest — FastAPI backend: API game + phục vụ frontend tĩnh."""
import time
from contextlib import asynccontextmanager
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import case, func, select, update

from . import auth
from .auth import admin_user, current_user
from .db import engine, events, init_db, inventory, profiles, progress, submissions
from .judge import MAX_CODE_LENGTH, judge
from .levels import CHAPTERS, ITEMS, LEVELS, LEVELS_BY_ID, public_level

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"



@asynccontextmanager
async def lifespan(_app):
    init_db()
    yield


app = FastAPI(title="Python Quest API", docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan)


# ------------------------------------------------------------------ helpers

class CodeIn(BaseModel):
    code: str = Field(max_length=MAX_CODE_LENGTH)


class EventIn(BaseModel):
    type: str = Field(pattern="^(login|open_level)$")
    level_id: int | None = None


class AdminUserIn(BaseModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=24)
    role: str | None = Field(default=None, pattern="^(player|admin)$")
    banned: bool | None = None


_last_judge = {}


def throttle(user_id, seconds=1.5):
    now = time.monotonic()
    if now - _last_judge.get(user_id, 0) < seconds:
        raise HTTPException(429, "Bạn chạy code nhanh quá, đợi một chút nhé.")
    _last_judge[user_id] = now


def log_event(conn, user_id, type_, level_id=None, detail=None):
    conn.execute(events.insert().values(user_id=user_id, type=type_, level_id=level_id, detail=detail))


def user_progress(conn, user_id):
    rows = conn.execute(select(progress).where(progress.c.user_id == user_id)).mappings().all()
    return {r["level_id"]: dict(r) for r in rows}


def is_unlocked(level_id, prog, user):
    if user["role"] == "admin" or level_id == LEVELS[0]["id"]:
        return True
    prev = prog.get(level_id - 1)
    return bool(prev and prev["completed"])


def get_level_or_404(level_id, user, conn):
    lv = LEVELS_BY_ID.get(level_id)
    if lv is None:
        raise HTTPException(404, "Không tìm thấy level.")
    prog = user_progress(conn, user["id"])
    if not is_unlocked(level_id, prog, user):
        raise HTTPException(403, "Level này chưa mở khóa. Hãy hoàn thành level trước đó.")
    return lv, prog.get(level_id)


def upsert_progress(conn, user_id, level_id, **values):
    exists = conn.execute(select(progress.c.level_id).where(
        progress.c.user_id == user_id, progress.c.level_id == level_id)).first()
    if exists:
        conn.execute(update(progress).where(progress.c.user_id == user_id, progress.c.level_id == level_id).values(**values))
    else:
        conn.execute(progress.insert().values(user_id=user_id, level_id=level_id, **values))


def leaderboard_rows(conn):
    score = func.coalesce(func.sum(progress.c.best_score), 0)
    done = func.coalesce(func.sum(case((progress.c.completed.is_(True), 1), else_=0)), 0)
    q = (select(profiles.c.id, profiles.c.display_name, score.label("score"), done.label("done"))
         .select_from(profiles.outerjoin(progress, progress.c.user_id == profiles.c.id))
         .where(profiles.c.banned.is_(False))
         .group_by(profiles.c.id, profiles.c.display_name)
         .order_by(score.desc(), done.desc(), profiles.c.display_name))
    return [dict(r) for r in conn.execute(q).mappings().all()]


def iso(value):
    return value.isoformat() if value else None


# ------------------------------------------------------------------ public

@app.get("/api/config")
def config():
    return {"auth_mode": auth.AUTH_MODE, "supabase_url": auth.SUPABASE_URL, "supabase_anon_key": auth.SUPABASE_ANON_KEY}


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/leaderboard")
def leaderboard():
    with engine.connect() as conn:
        rows = [r for r in leaderboard_rows(conn) if r["score"] > 0][:50]
    return [{"rank": i + 1, "name": r["display_name"], "score": int(r["score"]), "done": int(r["done"])}
            for i, r in enumerate(rows)]


# ------------------------------------------------------------------ player

@app.get("/api/me")
def me(user=Depends(current_user)):
    with engine.connect() as conn:
        prog = user_progress(conn, user["id"])
        rows = leaderboard_rows(conn)
    rows = [r for r in rows if r["score"] > 0]
    rank = next((i + 1 for i, r in enumerate(rows) if r["id"] == user["id"]), None)
    return {
        "id": user["id"], "email": user["email"], "display_name": user["display_name"], "role": user["role"],
        "score": sum(p["best_score"] for p in prog.values()),
        "completed": sum(1 for p in prog.values() if p["completed"]),
        "total_levels": len(LEVELS), "rank": rank,
    }


@app.post("/api/events")
def track(body: EventIn, user=Depends(current_user)):
    with engine.begin() as conn:
        log_event(conn, user["id"], body.type, body.level_id)
    return {"ok": True}


@app.get("/api/levels")
def list_levels(user=Depends(current_user)):
    with engine.connect() as conn:
        prog = user_progress(conn, user["id"])
    out = []
    for lv in LEVELS:
        p = prog.get(lv["id"], {})
        out.append({
            "id": lv["id"], "chapter": lv["chapter"], "title": lv["title"], "kind": lv["kind"], "scene": lv["scene"],
            "unlocked": is_unlocked(lv["id"], prog, user), "completed": bool(p.get("completed")),
            "best_score": p.get("best_score", 0), "attempts": p.get("attempts", 0), "reward": lv["reward"],
        })
    return {"chapters": CHAPTERS, "levels": out}


@app.get("/api/levels/{level_id}")
def get_level(level_id: int, user=Depends(current_user)):
    with engine.connect() as conn:
        lv, p = get_level_or_404(level_id, user, conn)
    p = p or {}
    data = public_level(lv)
    data["hints"] = lv["hints"][: p.get("hints_used", 0)]
    data["progress"] = {"best_score": p.get("best_score", 0), "completed": bool(p.get("completed")),
                        "attempts": p.get("attempts", 0), "hints_used": p.get("hints_used", 0)}
    data["saved_code"] = p.get("last_code")
    data["next_level"] = level_id + 1 if level_id + 1 in LEVELS_BY_ID else None
    return data


@app.post("/api/levels/{level_id}/hint")
def take_hint(level_id: int, user=Depends(current_user)):
    with engine.begin() as conn:
        lv, p = get_level_or_404(level_id, user, conn)
        used = (p or {}).get("hints_used", 0)
        if used < len(lv["hints"]):
            used += 1
            upsert_progress(conn, user["id"], level_id, hints_used=used)
            log_event(conn, user["id"], "hint", level_id, str(used))
    return {"hints": lv["hints"][:used], "hints_used": used}


@app.post("/api/levels/{level_id}/run")
async def run_code(level_id: int, body: CodeIn, user=Depends(current_user)):
    with engine.connect() as conn:
        lv, _ = get_level_or_404(level_id, user, conn)
    throttle(user["id"])
    result = await judge(lv, body.code, include_hidden=False)
    with engine.begin() as conn:
        upsert_progress(conn, user["id"], level_id, last_code=body.code)
        log_event(conn, user["id"], "run", level_id, result["error_type"])
    return result


@app.post("/api/levels/{level_id}/submit")
async def submit_code(level_id: int, body: CodeIn, user=Depends(current_user)):
    with engine.connect() as conn:
        lv, p = get_level_or_404(level_id, user, conn)
    throttle(user["id"])
    result = await judge(lv, body.code, include_hidden=True)
    p = p or {}
    hints_used = p.get("hints_used", 0)
    score = max(0, round(100 * result["passed"] / result["total"]) - 10 * hints_used)
    completed = result["status"] == "passed"
    new_item = None
    with engine.begin() as conn:
        conn.execute(submissions.insert().values(
            user_id=user["id"], level_id=level_id, code=body.code, passed=result["passed"],
            total=result["total"], score=score, error_type=result["error_type"]))
        values = {"attempts": p.get("attempts", 0) + 1, "best_score": max(score, p.get("best_score", 0)),
                  "last_code": body.code}
        if completed and not p.get("completed"):
            values.update(completed=True, completed_at=datetime.now(timezone.utc))
        upsert_progress(conn, user["id"], level_id, **values)
        if completed:
            item = lv["reward"]
            owned = conn.execute(select(inventory.c.item_id).where(
                inventory.c.user_id == user["id"], inventory.c.item_id == item["id"])).first()
            if not owned:
                conn.execute(inventory.insert().values(user_id=user["id"], item_id=item["id"]))
                new_item = item
        log_event(conn, user["id"], "submit", level_id, result["error_type"])
    result.update(score=score, best_score=values["best_score"], hints_used=hints_used, new_item=new_item,
                  next_level=level_id + 1 if completed and level_id + 1 in LEVELS_BY_ID else None)
    return result


@app.get("/api/inventory")
def get_inventory(user=Depends(current_user)):
    with engine.connect() as conn:
        rows = conn.execute(select(inventory).where(inventory.c.user_id == user["id"])
                            .order_by(inventory.c.acquired_at)).mappings().all()
    return [{**ITEMS[r["item_id"]], "acquired_at": iso(r["acquired_at"])} for r in rows if r["item_id"] in ITEMS]


@app.get("/api/submissions")
def my_submissions(level_id: int | None = None, user=Depends(current_user)):
    q = select(submissions.c.id, submissions.c.level_id, submissions.c.passed, submissions.c.total,
               submissions.c.score, submissions.c.error_type, submissions.c.created_at
               ).where(submissions.c.user_id == user["id"]).order_by(submissions.c.id.desc()).limit(30)
    if level_id is not None:
        q = q.where(submissions.c.level_id == level_id)
    with engine.connect() as conn:
        rows = conn.execute(q).mappings().all()
    return [{**r, "created_at": iso(r["created_at"])} for r in rows]


# ------------------------------------------------------------------ admin

@app.get("/api/admin/users")
def admin_users(_=Depends(admin_user)):
    with engine.connect() as conn:
        users = conn.execute(select(profiles).order_by(profiles.c.created_at.desc())).mappings().all()
        scores = {r["id"]: r for r in leaderboard_rows(conn)}
        subs = dict(conn.execute(select(submissions.c.user_id, func.count()).group_by(submissions.c.user_id)).all())
    return [{
        "id": u["id"], "email": u["email"], "display_name": u["display_name"], "role": u["role"],
        "banned": u["banned"], "created_at": iso(u["created_at"]), "last_seen": iso(u["last_seen"]),
        "score": int(scores.get(u["id"], {}).get("score") or 0), "done": int(scores.get(u["id"], {}).get("done") or 0),
        "submissions": subs.get(u["id"], 0),
    } for u in users]


@app.patch("/api/admin/users/{user_id}")
def admin_update_user(user_id: str, body: AdminUserIn, admin=Depends(admin_user)):
    values = body.model_dump(exclude_none=True)
    if "display_name" in values:
        values["display_name"] = " ".join(values["display_name"].split())
        if len(values["display_name"]) < 2:
            raise HTTPException(422, "Tên hiển thị quá ngắn.")
    if not values:
        raise HTTPException(422, "Không có thay đổi.")
    if user_id == admin["id"] and ({"role", "banned"} & values.keys()):
        raise HTTPException(400, "Không thể tự đổi quyền hoặc tự khóa tài khoản của mình.")
    with engine.begin() as conn:
        res = conn.execute(update(profiles).where(profiles.c.id == user_id).values(**values))
        if res.rowcount == 0:
            raise HTTPException(404, "Không tìm thấy người dùng.")
    return {"ok": True, **values}


@app.get("/api/admin/stats")
def admin_stats(_=Depends(admin_user)):
    with engine.connect() as conn:
        total_users = conn.execute(select(func.count()).select_from(profiles)).scalar()
        total_subs = conn.execute(select(func.count()).select_from(submissions)).scalar()
        per_level = conn.execute(select(
            submissions.c.level_id, func.count().label("attempts"),
            func.count(func.distinct(submissions.c.user_id)).label("players"),
            func.sum(case((submissions.c.error_type == "ok", 1), else_=0)).label("passes"),
        ).group_by(submissions.c.level_id)).mappings().all()
        completions = dict(conn.execute(select(progress.c.level_id, func.count())
                                        .where(progress.c.completed.is_(True)).group_by(progress.c.level_id)).all())
        hints = dict(conn.execute(select(progress.c.level_id, func.avg(progress.c.hints_used))
                                  .group_by(progress.c.level_id)).all())
        recent = conn.execute(select(events.c.user_id, events.c.type, events.c.detail, events.c.created_at)
                              .order_by(events.c.id.desc()).limit(20000)).all()

    by_level = {r["level_id"]: r for r in per_level}
    levels = []
    for lv in LEVELS:
        r = by_level.get(lv["id"])
        attempts = r["attempts"] if r else 0
        levels.append({
            "id": lv["id"], "title": lv["title"], "attempts": attempts, "players": r["players"] if r else 0,
            "pass_rate": round(100 * (r["passes"] or 0) / attempts) if attempts else None,
            "completed_by": completions.get(lv["id"], 0), "avg_hints": round(float(hints.get(lv["id"]) or 0), 2),
        })

    errors = Counter(d for _, t, d, _ in recent if t in ("run", "submit") and d)
    daily = defaultdict(set)
    for user_id, _, _, created in recent:
        if created:
            daily[created.date().isoformat()].add(user_id)
    days = sorted(daily)[-14:]
    return {
        "total_users": total_users, "total_submissions": total_subs,
        "events": Counter(t for _, t, _, _ in recent),
        "error_types": errors, "levels": levels,
        "daily_active": [{"day": d, "users": len(daily[d])} for d in days],
    }


@app.get("/cdn/{path:path}", include_in_schema=False)
def pygbag_cdn(path: str):
    # Khi chạy trên localhost, pygbag tải wheel pygame từ /cdn/... của chính server (như test server của nó).
    return RedirectResponse(f"https://pygame-web.github.io/cdn/{path}")


# Frontend tĩnh (đặt cuối để không che các route /api).
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
