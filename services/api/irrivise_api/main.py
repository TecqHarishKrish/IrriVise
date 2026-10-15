"""Local-only API; science jobs are processed by a separate worker."""
import json
import re
from datetime import date
from pathlib import Path
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from irrivise_api.storage import ROOT, connect, ident, many, now, one
from irrivise_api.auth import Actor, FEATURES, PRIMARY_ADMIN_EMAIL, configuration_status, current_actor, effective_actor, enabled_features, require_admin, require_feature, require_primary_admin
from irrivise_core.data import checksum, load_weather
from irrivise_api.analyst import available as analyst_available, brief as analyst_brief

app = FastAPI(title="IrriVise API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["GET", "POST", "PATCH"], allow_headers=["*"])


class ProjectIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    crop: str = Field(default="maize", pattern="^maize$")


class ScenarioIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    budget_mm: float = Field(ge=0, le=2000)
    daily_max_mm: float = Field(ge=0, le=100)
    observation_budget: int = Field(ge=0, le=90)


class SimulationIn(BaseModel):
    scenario_id: str
    controller: str = Field(pattern="^(fixed|threshold|deficit|conservative|carat)$")
    dataset_id: str = "sample"
    seed: int = Field(default=42, ge=0, le=2**31 - 1)


class TrainingIn(BaseModel):
    scenario_id: str
    preset: str = Field(default="cpu_quick", pattern="^cpu_quick$")
    seed: int = Field(default=42, ge=0, le=2**31 - 1)
    total_timesteps: int = Field(default=2048, ge=256, le=10000)


class WeatherFetchIn(BaseModel):
    scenario_id: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    start: date
    end: date
    time_standard: str = Field(default="UTC", pattern="^(UTC|LST)$")


class FeatureAccessIn(BaseModel):
    enabled: bool


class AccountRoleIn(BaseModel):
    role: str = Field(pattern="^(admin|user)$")


class AnalystRequest(BaseModel):
    run_id: str
    question: str = Field(default="Summarize the latest model evidence.", min_length=1, max_length=1000)


def owned_project(db, actor: Actor, project_id: str) -> dict:
    item = one(db, "SELECT * FROM projects WHERE id=? AND account_id=?", (project_id, actor.id))
    if not item:
        raise HTTPException(404, "Project not found")
    return item


def owned_scenario(db, actor: Actor, scenario_id: str) -> dict:
    item = one(db, "SELECT scenarios.* FROM scenarios JOIN projects ON projects.id=scenarios.project_id WHERE scenarios.id=? AND projects.account_id=?", (scenario_id, actor.id))
    if not item:
        raise HTTPException(404, "Scenario not found")
    return item


def owned_job(db, actor: Actor, job_id: str) -> dict:
    item = one(db, "SELECT jobs.* FROM jobs JOIN scenarios ON scenarios.id=jobs.scenario_id JOIN projects ON projects.id=scenarios.project_id WHERE jobs.id=? AND projects.account_id=?", (job_id, actor.id))
    if not item:
        raise HTTPException(404, "Job not found")
    return item


def owned_run(db, actor: Actor, run_id: str) -> dict:
    item = one(db, "SELECT runs.* FROM runs JOIN scenarios ON scenarios.id=runs.scenario_id JOIN projects ON projects.id=scenarios.project_id WHERE runs.id=? AND projects.account_id=?", (run_id, actor.id))
    if not item:
        raise HTTPException(404, "Run not found")
    return item


def required(db, table: str, key: str) -> dict:
    if table not in {"projects", "scenarios", "jobs", "runs"}:
        raise ValueError("Invalid table")
    row = one(db, f"SELECT * FROM {table} WHERE id=?", (key,))
    if not row:
        raise HTTPException(404, "Record not found")
    return row


@app.get("/health")
def health():
    with connect() as db:
        db.execute("SELECT 1")
        jobs = one(db, "SELECT COUNT(*) AS count FROM jobs WHERE status='running'")
    return {"api": "ok", "database": "ok", "running_jobs": jobs["count"], "sample_dataset": (ROOT / "data/sample/weather.csv").exists(), "auth": configuration_status()}


@app.get("/api/v1/access/me")
def access_me(actor: Actor = Depends(current_actor)):
    return {"id": actor.id, "email": actor.email, "role": actor.role, "features": enabled_features(actor.id, actor.role)}


@app.get("/api/v1/analyst/status")
def analyst_status(_: Actor = Depends(require_feature("analyst"))):
    return {"configured": analyst_available(), "provider": "groq", "purpose": "saved-run explanation only"}


@app.post("/api/v1/analyst/brief")
def analyst_run_brief(payload: AnalystRequest, actor: Actor = Depends(require_feature("analyst"))):
    with connect() as db:
        run = owned_run(db, actor, payload.run_id)
    trace = json.loads((ROOT / run["trace_path"]).read_text())
    safe_days = [{key: value for key, value in day.items() if key != "reference_storage_mm_evaluation_only"} for day in trace]
    summary = json.loads(run["summary_json"])
    return analyst_brief(summary, safe_days, payload.question)


@app.get("/api/v1/admin/accounts")
def admin_accounts(_: Actor = Depends(require_admin)):
    with connect() as db:
        accounts = many(db, "SELECT id,email,role,created_at,last_seen_at FROM accounts ORDER BY role DESC, email")
    return [{**account, "features": enabled_features(account["id"], account["role"])} for account in accounts]


@app.put("/api/v1/admin/accounts/{account_id}/features/{feature_key}")
def set_account_feature(account_id: str, feature_key: str, payload: FeatureAccessIn, _: Actor = Depends(require_admin)):
    if feature_key not in FEATURES:
        raise HTTPException(404, "Feature not found")
    with connect() as db:
        if not one(db, "SELECT id FROM accounts WHERE id=?", (account_id,)):
            raise HTTPException(404, "Account not found")
        db.execute("INSERT INTO account_features(account_id,feature_key,enabled,updated_at) VALUES (?,?,?,?) ON CONFLICT(account_id,feature_key) DO UPDATE SET enabled=excluded.enabled,updated_at=excluded.updated_at", (account_id, feature_key, int(payload.enabled), now()))
    return {"account_id": account_id, "feature_key": feature_key, "enabled": payload.enabled}


@app.put("/api/v1/admin/accounts/{account_id}/role")
def set_account_role(account_id: str, payload: AccountRoleIn, _: Actor = Depends(require_primary_admin)):
    with connect() as db:
        account = one(db, "SELECT id,email FROM accounts WHERE id=?", (account_id,))
        if not account:
            raise HTTPException(404, "Account not found")
        if account["email"] == PRIMARY_ADMIN_EMAIL and payload.role != "admin":
            raise HTTPException(422, "The primary administrator must remain an administrator.")
        db.execute("UPDATE accounts SET role=? WHERE id=?", (payload.role, account_id))
    return {"account_id": account_id, "role": payload.role}


@app.get("/api/v1/projects")
def projects(actor: Actor = Depends(require_feature("projects"))):
    with connect() as db:
        return many(db, "SELECT * FROM projects WHERE archived=0 AND account_id=? ORDER BY created_at DESC", (actor.id,))


@app.post("/api/v1/projects", status_code=201)
def create_project(payload: ProjectIn, actor: Actor = Depends(require_feature("projects"))):
    item = {"id": ident(), **payload.model_dump(), "account_id": actor.id, "created_at": now(), "archived": 0}
    with connect() as db:
        db.execute("INSERT INTO projects(id,name,crop,account_id,created_at,archived) VALUES (:id,:name,:crop,:account_id,:created_at,:archived)", item)
    return item


@app.get("/api/v1/projects/{project_id}")
def project(project_id: str, actor: Actor = Depends(require_feature("projects"))):
    with connect() as db:
        return owned_project(db, actor, project_id)


@app.get("/api/v1/projects/{project_id}/scenarios")
def scenarios(project_id: str, actor: Actor = Depends(require_feature("projects"))):
    with connect() as db:
        owned_project(db, actor, project_id)
        return many(db, "SELECT * FROM scenarios WHERE project_id=? ORDER BY created_at DESC", (project_id,))


@app.post("/api/v1/projects/{project_id}/scenarios", status_code=201)
def create_scenario(project_id: str, payload: ScenarioIn, actor: Actor = Depends(require_feature("projects"))):
    item = {"id": ident(), "project_id": project_id, **payload.model_dump(), "created_at": now()}
    with connect() as db:
        owned_project(db, actor, project_id)
        db.execute("INSERT INTO scenarios(id,project_id,name,budget_mm,daily_max_mm,observation_budget,created_at) VALUES (:id,:project_id,:name,:budget_mm,:daily_max_mm,:observation_budget,:created_at)", item)
    return item


@app.get("/api/v1/scenarios/{scenario_id}")
def scenario(scenario_id: str, actor: Actor = Depends(require_feature("projects"))):
    with connect() as db:
        return owned_scenario(db, actor, scenario_id)


@app.get("/api/v1/datasets")
def datasets(_: Actor = Depends(require_feature("weather"))):
    path = ROOT / "data/sample/weather.csv"
    if not path.exists():
        return []
    rows = load_weather(path)
    results = [{"id": "sample", "source": "synthetic demonstration", "days": len(rows), "start": rows[0].date, "end": rows[-1].date, "checksum_sha256": checksum(path), "units": {"rain_mm": "mm/day", "eto_mm": "mm/day", "tmin_c": "°C", "tmax_c": "°C"}}]
    manifests = ROOT / "data/manifests"
    if manifests.exists():
        results.extend(json.loads(item.read_text()) for item in sorted(manifests.glob("nasa-*.json")))
    return results


@app.post("/api/v1/datasets/nasa-power", status_code=202)
def enqueue_power(payload: WeatherFetchIn, actor: Actor = Depends(require_feature("weather"))):
    if payload.end < payload.start or (payload.end - payload.start).days > 730 or payload.end >= date.today():
        raise HTTPException(422, "Historical date range must be in the past and at most 731 days")
    with connect() as db:
        owned_scenario(db, actor, payload.scenario_id)
        job_id = ident()
        db.execute("INSERT INTO jobs(id,kind,scenario_id,controller,seed,status,payload_json,created_at) VALUES (?,?,?, ?,0,'queued',?,?)", (job_id, "weather", payload.scenario_id, "NASA_POWER", payload.model_dump_json(), now()))
    return {"job_id": job_id, "status": "queued", "status_url": f"/api/v1/jobs/{job_id}"}


@app.get("/api/v1/datasets/sample/preview")
def preview(_: Actor = Depends(require_feature("weather"))):
    return [row.__dict__ for row in load_weather(ROOT / "data/sample/weather.csv")[:10]]


@app.get("/api/v1/datasets/{dataset_id}/preview")
def dataset_preview(dataset_id: str, _: Actor = Depends(require_feature("weather"))):
    if not re.fullmatch(r"[0-9a-f]{64}", dataset_id):
        raise HTTPException(404, "Dataset not found")
    path = ROOT / "data/processed" / f"nasa-{dataset_id}.csv"
    if not path.exists():
        raise HTTPException(404, "Dataset not found")
    return [row.__dict__ for row in load_weather(path)[:10]]


@app.post("/api/v1/simulations", status_code=202)
def enqueue_simulation(payload: SimulationIn, actor: Actor = Depends(require_feature("simulation"))):
    with connect() as db:
        owned_scenario(db, actor, payload.scenario_id)
        if payload.dataset_id != "sample":
            if not re.fullmatch(r"[0-9a-f]{64}", payload.dataset_id):
                raise HTTPException(404, "Dataset not found")
            path = ROOT / "data/processed" / f"nasa-{payload.dataset_id}.csv"
            if not path.exists():
                raise HTTPException(404, "Dataset not found")
            length = len(load_weather(path))
            if length < 140 or length > 200:
                raise HTTPException(422, "Current maize simulator requires a 140–200 day historical dataset")
        job_id = ident()
        db.execute("INSERT INTO jobs(id,kind,scenario_id,controller,seed,status,payload_json,created_at) VALUES (?,?,?,?,?,'queued',?,?)", (job_id, "simulation", payload.scenario_id, payload.controller, payload.seed, payload.model_dump_json(), now()))
    return {"job_id": job_id, "status": "queued", "status_url": f"/api/v1/jobs/{job_id}"}


@app.post("/api/v1/training", status_code=202)
def enqueue_training(payload: TrainingIn, actor: Actor = Depends(require_feature("training"))):
    with connect() as db:
        owned_scenario(db, actor, payload.scenario_id)
        job_id = ident()
        db.execute("INSERT INTO jobs(id,kind,scenario_id,controller,seed,status,total_steps,created_at) VALUES (?,?,?,?,?,'queued',?,?)", (job_id, "training", payload.scenario_id, "PPO", payload.seed, payload.total_timesteps, now()))
    return {"job_id": job_id, "status": "queued", "status_url": f"/api/v1/jobs/{job_id}"}


@app.get("/api/v1/models")
def models(_: Actor = Depends(require_feature("training"))):
    directory = ROOT / "artifacts/models"
    if not directory.exists():
        return []
    return [json.loads(path.read_text()) for path in sorted(directory.glob("*.json"))]


@app.get("/api/v1/jobs")
def jobs(actor: Actor = Depends(effective_actor)):
    with connect() as db:
        return many(db, "SELECT jobs.* FROM jobs JOIN scenarios ON scenarios.id=jobs.scenario_id JOIN projects ON projects.id=scenarios.project_id WHERE projects.account_id=? ORDER BY jobs.created_at DESC LIMIT 100", (actor.id,))


@app.get("/api/v1/jobs/{job_id}")
def job(job_id: str, actor: Actor = Depends(effective_actor)):
    with connect() as db:
        return owned_job(db, actor, job_id)


@app.post("/api/v1/jobs/{job_id}/cancel")
def cancel(job_id: str, actor: Actor = Depends(effective_actor)):
    with connect() as db:
        item = owned_job(db, actor, job_id)
        if item["status"] == "queued":
            db.execute("UPDATE jobs SET status='cancelled',cancel_requested=1,finished_at=? WHERE id=?", (now(), job_id))
        elif item["status"] == "running":
            db.execute("UPDATE jobs SET cancel_requested=1 WHERE id=?", (job_id,))
        return owned_job(db, actor, job_id)


@app.get("/api/v1/simulations")
def runs(actor: Actor = Depends(require_feature("analytics"))):
    with connect() as db:
        result = many(db, "SELECT runs.* FROM runs JOIN scenarios ON scenarios.id=runs.scenario_id JOIN projects ON projects.id=scenarios.project_id WHERE projects.account_id=? ORDER BY runs.created_at DESC LIMIT 100", (actor.id,))
    return [{**r, "summary": json.loads(r.pop("summary_json"))} for r in result]


@app.get("/api/v1/simulations/{run_id}")
def run(run_id: str, actor: Actor = Depends(require_feature("analytics"))):
    with connect() as db:
        item = owned_run(db, actor, run_id)
    item["summary"] = json.loads(item.pop("summary_json"))
    return item


@app.get("/api/v1/simulations/{run_id}/daily")
def daily(run_id: str, actor: Actor = Depends(require_feature("digital_twin"))):
    with connect() as db:
        item = owned_run(db, actor, run_id)
    rows = json.loads((ROOT / item["trace_path"]).read_text())
    return [{key: value for key, value in row.items() if key != "reference_storage_mm_evaluation_only"} for row in rows]


@app.get("/api/v1/simulations/{run_id}/evaluation")
def evaluation(run_id: str, actor: Actor = Depends(require_feature("digital_twin"))):
    """Post-run evaluation only: includes hidden simulated reference values."""
    with connect() as db:
        item = owned_run(db, actor, run_id)
    return json.loads((ROOT / item["trace_path"]).read_text())
