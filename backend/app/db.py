"""Lưu trữ bằng SQLAlchemy Core: PostgreSQL (Supabase) khi deploy, SQLite khi chạy local."""
import os

from sqlalchemy import (Boolean, Column, DateTime, ForeignKey, Integer, MetaData, String, Table, Text,
                        create_engine, func, text)

metadata = MetaData()

profiles = Table(
    "pq_profiles", metadata,
    Column("id", String(64), primary_key=True),  # id người dùng từ Supabase Auth
    Column("email", String(255), nullable=False),
    Column("display_name", String(40), nullable=False),
    Column("role", String(10), nullable=False, default="player"),  # player | admin
    Column("banned", Boolean, nullable=False, default=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("last_seen", DateTime(timezone=True), server_default=func.now()),
)

progress = Table(
    "pq_progress", metadata,
    Column("user_id", String(64), ForeignKey("pq_profiles.id", ondelete="CASCADE"), primary_key=True),
    Column("level_id", Integer, primary_key=True),
    Column("best_score", Integer, nullable=False, default=0),
    Column("completed", Boolean, nullable=False, default=False),
    Column("hints_used", Integer, nullable=False, default=0),
    Column("attempts", Integer, nullable=False, default=0),
    Column("last_code", Text),
    Column("completed_at", DateTime(timezone=True)),
)

submissions = Table(
    "pq_submissions", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String(64), ForeignKey("pq_profiles.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("level_id", Integer, nullable=False, index=True),
    Column("code", Text, nullable=False),
    Column("passed", Integer, nullable=False),
    Column("total", Integer, nullable=False),
    Column("score", Integer, nullable=False),
    Column("error_type", String(20), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

inventory = Table(
    "pq_inventory", metadata,
    Column("user_id", String(64), ForeignKey("pq_profiles.id", ondelete="CASCADE"), primary_key=True),
    Column("item_id", String(40), primary_key=True),
    Column("acquired_at", DateTime(timezone=True), server_default=func.now()),
)

events = Table(
    "pq_events", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String(64), index=True),
    Column("type", String(30), nullable=False),  # login | open_level | run | submit | hint
    Column("level_id", Integer),
    Column("detail", String(40)),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), index=True),
)


def _database_url():
    url = os.environ.get("DATABASE_URL", "sqlite:///./python_quest.db")
    # Supabase/Render đưa URL dạng postgres:// hoặc postgresql:// -> dùng driver psycopg v3.
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


DATABASE_URL = _database_url()
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    # prepare_threshold=None: tương thích pooler của Supabase (pgbouncer chế độ transaction).
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {"prepare_threshold": None},
)


def init_db():
    metadata.create_all(engine)
    if engine.dialect.name == "postgresql":
        # Supabase mở schema public qua Data API bằng anon key (key này công khai trên frontend).
        # Bật RLS và không tạo policy nào => chỉ backend (role postgres) đọc/ghi được.
        with engine.begin() as conn:
            for table in metadata.sorted_tables:
                conn.execute(text(f'ALTER TABLE "{table.name}" ENABLE ROW LEVEL SECURITY'))
