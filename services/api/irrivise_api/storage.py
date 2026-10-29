"""SQLite metadata and durable single-worker job queue."""
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DB = ROOT / "data" / "irrivise.sqlite3"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, name TEXT NOT NULL, crop TEXT NOT NULL, created_at TEXT NOT NULL, archived INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, role TEXT NOT NULL CHECK(role IN ('admin','user')), created_at TEXT NOT NULL, last_seen_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS account_features(account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE, feature_key TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)), updated_at TEXT NOT NULL, PRIMARY KEY(account_id, feature_key));
    CREATE TABLE IF NOT EXISTS scenarios(id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), name TEXT NOT NULL, budget_mm REAL NOT NULL, daily_max_mm REAL NOT NULL, observation_budget INTEGER NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, kind TEXT NOT NULL, scenario_id TEXT NOT NULL REFERENCES scenarios(id), controller TEXT NOT NULL, seed INTEGER NOT NULL, status TEXT NOT NULL, progress INTEGER NOT NULL DEFAULT 0, current_step INTEGER NOT NULL DEFAULT 0, total_steps INTEGER NOT NULL DEFAULT 0, cancel_requested INTEGER NOT NULL DEFAULT 0, payload_json TEXT, dataset_id TEXT, created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT, error TEXT, run_id TEXT);
    CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, job_id TEXT UNIQUE NOT NULL REFERENCES jobs(id), scenario_id TEXT NOT NULL REFERENCES scenarios(id), controller TEXT NOT NULL, summary_json TEXT NOT NULL, trace_path TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS experiments(id TEXT PRIMARY KEY, scenario_id TEXT NOT NULL REFERENCES scenarios(id), account_id TEXT REFERENCES accounts(id), dataset_id TEXT NOT NULL, seed INTEGER NOT NULL, controllers_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS experiment_jobs(experiment_id TEXT NOT NULL REFERENCES experiments(id), job_id TEXT NOT NULL REFERENCES jobs(id), controller TEXT NOT NULL, PRIMARY KEY(experiment_id, job_id));
    """)
    columns = {row[1] for row in db.execute("PRAGMA table_info(jobs)")}
    for name in ("current_step", "total_steps", "payload_json", "dataset_id"):
        if name not in columns:
            definition = "INTEGER NOT NULL DEFAULT 0" if name in {"current_step", "total_steps"} else "TEXT"
            db.execute(f"ALTER TABLE jobs ADD COLUMN {name} {definition}")
    project_columns = {row[1] for row in db.execute("PRAGMA table_info(projects)")}
    if "account_id" not in project_columns:
        db.execute("ALTER TABLE projects ADD COLUMN account_id TEXT REFERENCES accounts(id)")
    exp_columns = {row[1] for row in db.execute("PRAGMA table_info(experiments)")}
    if "account_id" not in exp_columns:
        db.execute("ALTER TABLE experiments ADD COLUMN account_id TEXT REFERENCES accounts(id)")
    return db


def one(db: sqlite3.Connection, query: str, params: tuple = ()) -> dict | None:
    row = db.execute(query, params).fetchone()
    return dict(row) if row else None


def many(db: sqlite3.Connection, query: str, params: tuple = ()) -> list[dict]:
    return [dict(row) for row in db.execute(query, params).fetchall()]


def ident() -> str:
    return str(uuid.uuid4())
