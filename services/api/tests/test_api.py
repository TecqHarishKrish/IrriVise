"""API contract, persistence, validation and safety."""
import io
import zipfile

from conftest import run_next_job


def test_health_and_defaults(client):
    h = client.get("/api/v1/health").json()
    assert h["api"] == "ok" and h["database"] == "ok" and h["schema_revision"] == "0001" and h["sample_dataset"]
    assert client.get("/health").status_code == 200
    d = client.get("/api/v1/config/defaults").json()
    assert d["actions_mm"] == [0.0, 5.0, 10.0, 15.0, 20.0] and {"cpu_quick", "cpu_standard", "cpu_research"} <= set(d["training_presets"])
    assert any(m["key"] == "carat_full" and m["needs_model"] for m in d["methods"])
    assert client.get("/openapi.json").json()["info"]["title"] == "IrriVise API"


def test_project_and_scenario_crud_survive_restart(client, tmp_path):
    p = client.post("/api/v1/projects", json={"name": "North field", "description": "Test"}).json()
    s = client.post(f"/api/v1/projects/{p['id']}/scenarios", json={"name": "Season A", "seasonal_budget_mm": 200, "observation_budget": 5}).json()
    assert s["validation_status"] == "incomplete" and s["season_length_days"] == 140
    ds = client.get("/api/v1/datasets").json()[0]
    s2 = client.patch(f"/api/v1/scenarios/{s['id']}", json={"dataset_id": ds["id"], "daily_max_mm": 15}).json()
    assert s2["validation_status"] == "valid" and s2["daily_max_mm"] == 15 and s2["scenario_sha256"] != s["scenario_sha256"]
    client.patch(f"/api/v1/projects/{p['id']}", json={"name": "North field 2"})
    assert client.delete(f"/api/v1/projects/{p['id']}").json()["archived"] is True
    assert all(x["id"] != p["id"] for x in client.get("/api/v1/projects").json())
    assert any(x["id"] == p["id"] for x in client.get("/api/v1/projects?include_archived=true").json())
    # restart: new engine on the same database file
    from irrivise_api.db import session
    session.dispose_all()
    assert client.get(f"/api/v1/scenarios/{s['id']}").json()["name"] == "Season A"


def test_validation_errors_and_unknown_ids(client):
    r = client.post("/api/v1/projects", json={"name": "x"})
    assert r.status_code == 422 and r.json()["code"] == "validation_error" and "request_id" in r.json()
    assert client.post("/api/v1/projects", json={"name": "<script>alert(1)</script>"}).status_code == 422
    p = client.post("/api/v1/projects", json={"name": "Field"}).json()
    bad = client.post(f"/api/v1/projects/{p['id']}/scenarios", json={"name": "S", "planting_mmdd": "02-30"})
    assert bad.status_code == 422
    unknown_soil = client.post(f"/api/v1/projects/{p['id']}/scenarios", json={"name": "Soil", "soil_profile": "moon_dust"})
    assert unknown_soil.status_code == 422 and unknown_soil.json()["code"] == "invalid_scenario"
    bad_adv = client.post(f"/api/v1/projects/{p['id']}/scenarios", json={"name": "Adv", "advanced": {"carat": {"horizon_days": 99}}})
    assert bad_adv.status_code == 422
    for path in ("/api/v1/projects/nope", "/api/v1/simulations/nope", "/api/v1/jobs/nope", "/api/v1/models/nope", "/api/v1/experiments/nope"):
        r = client.get(path)
        assert r.status_code == 404 and r.json()["code"] == "not_found", path


def test_csv_import_validation_and_limits(client):
    good = "date,rain_mm,eto_mm,tmin_c,tmax_c\n2020-01-01,0,4,20,30\n2020-01-02,NaN,4,20,30\n"
    r = client.post("/api/v1/datasets/import", files={"file": ("w.csv", good, "text/csv")}, data={"name": "Station"})
    assert r.status_code == 201 and r.json()["rows"] == 1 and r.json()["validation"]["quarantined_count"] == 1
    for text in ("", "date,rain_mm,eto_mm,tmin_c,tmax_c\n2020-01-01,-3,4,20,30\n", "date,rain\n2020-01-01,1\n"):
        bad = client.post("/api/v1/datasets/import", files={"file": ("w.csv", text, "text/csv")}, data={"name": "Bad"})
        assert bad.status_code == 422 and bad.json()["code"] == "invalid_weather_csv"
    assert client.post("/api/v1/datasets/import", files={"file": ("w.exe", "x", "application/x-msdownload")}, data={"name": "Exe"}).status_code == 415
    big = "date,rain_mm,eto_mm,tmin_c,tmax_c\n" + "2020-01-01,0,4,20,30\n" * 300_000
    assert client.post("/api/v1/datasets/import", files={"file": ("big.csv", big, "text/csv")}, data={"name": "Big"}).status_code == 413
    sample = next(d for d in client.get("/api/v1/datasets").json() if d["source"] == "sample")
    assert client.delete(f"/api/v1/datasets/{sample['id']}").status_code == 409
    preview = client.get(f"/api/v1/datasets/{sample['id']}/preview").json()
    assert len(preview["series"]) <= 400 and preview["split"]["test"] == ["2020", "2021", "2022", "2023"]


def test_nasa_power_request_validation(client):
    r = client.post("/api/v1/datasets/nasa-power", json={"latitude": 95, "longitude": 0, "start": "2020-01-01", "end": "2020-02-01"})
    assert r.status_code == 422
    r = client.post("/api/v1/datasets/nasa-power", json={"latitude": 10, "longitude": 78, "start": "2020-01-01", "end": "2099-01-01"})
    assert r.status_code == 422


def test_simulation_job_lifecycle_and_hidden_state_isolation(client, sample):
    sid = sample["scenario"]["id"]
    assert client.post("/api/v1/simulations", json={"scenario_id": sid, "method": "carat_full"}).json()["code"] == "model_required"
    job = client.post("/api/v1/simulations", json={"scenario_id": sid, "method": "lookahead_carat", "seed": 3, "aquacrop": True})
    assert job.status_code == 202 and job.json()["status"] == "queued" and job.json()["events_url"].endswith("/events")
    dup = client.post("/api/v1/simulations", json={"scenario_id": sid, "method": "lookahead_carat", "seed": 3, "aquacrop": True})
    assert dup.status_code == 409 and dup.json()["code"] == "duplicate_job"
    assert run_next_job() == job.json()["id"]
    done = client.get(f"/api/v1/jobs/{job.json()['id']}").json()
    assert done["status"] == "succeeded", done["error"]
    run_id = done["result"]["run_id"]
    run = client.get(f"/api/v1/simulations/{run_id}").json()
    assert run["split"] == "test" and run["season_id"] == "2020" and "hidden_parameters_evaluation_only" not in run["manifest"]
    assert run["summary"]["aquacrop"]["aquacrop_simulated_dry_yield_t_ha"] > 0
    daily = client.get(f"/api/v1/simulations/{run_id}/daily").json()
    assert daily["total"] == 140 and not any("true" in k or "reference" in k for k in daily["rows"][0])
    assert sum(r["applied_mm"] for r in daily["rows"]) == run["summary"]["seasonal_irrigation_mm"]
    decision = client.get(f"/api/v1/simulations/{run_id}/decisions?day=10").json()["rows"][0]
    assert decision["assessment_before"]["plausible_states"] and "true" not in str(decision.keys())
    evaluation = client.get(f"/api/v1/simulations/{run_id}/evaluation").json()
    assert "evaluation only" in evaluation["label"] and evaluation["rows"][0]["true_storage_mm"] > 0
    events = client.get(f"/api/v1/jobs/{done['id']}/events?format=json").json()
    seqs = [e["sequence"] for e in events["events"]]
    assert events["terminal"] and seqs == sorted(seqs) and len(set(seqs)) == len(seqs)
    later = client.get(f"/api/v1/jobs/{done['id']}/events?format=json&after={seqs[-2]}").json()["events"]
    assert [e["sequence"] for e in later] == [seqs[-1]]
    with client.stream("GET", f"/api/v1/jobs/{done['id']}/events") as stream:
        body = "".join(stream.iter_text())
    assert "event: progress" in body and "event: end" in body and f"id: {seqs[-1]}" in body
    analytics = client.get(f"/api/v1/analytics/overview?scenario_id={sid}").json()
    assert analytics["total_runs"] == 1


def test_cancel_queued_and_running_and_restart_recovery(client, sample):
    sid = sample["scenario"]["id"]
    q = client.post("/api/v1/simulations", json={"scenario_id": sid, "method": "fixed_schedule"}).json()
    c = client.post(f"/api/v1/jobs/{q['id']}/cancel").json()
    assert c["status"] == "cancelled"
    assert client.post(f"/api/v1/jobs/{q['id']}/cancel").status_code == 409
    assert run_next_job() is None
    from irrivise_api.db.models import Job
    from irrivise_api.db.session import session_scope
    from irrivise_api.services import jobs
    from irrivise_api.worker.tasks import execute
    r = client.post("/api/v1/simulations", json={"scenario_id": sid, "method": "fixed_schedule", "seed": 9}).json()
    with session_scope() as s:
        jobs.claim_next(s, "w", jobs.KINDS)
    client.post(f"/api/v1/jobs/{r['id']}/cancel")
    execute(r["id"])  # cooperative cancellation is honoured at the next checkpoint
    assert client.get(f"/api/v1/jobs/{r['id']}").json()["status"] == "cancelled"
    # worker death: a running job whose heartbeat stopped is marked interrupted, never silently resumed
    r2 = client.post("/api/v1/simulations", json={"scenario_id": sid, "method": "fixed_schedule", "seed": 10}).json()
    with session_scope() as s:
        jobs.claim_next(s, "dead-worker", jobs.KINDS)
    with session_scope() as s:
        s.get(Job, r2["id"]).heartbeat_at = None
        assert jobs.recover_stale(s, timeout_s=60) == [r2["id"]]
    final = client.get(f"/api/v1/jobs/{r2['id']}").json()
    assert final["status"] == "interrupted" and "re-queue" in final["error"].lower()


def test_idempotency_key_and_queue_cap(client, sample, monkeypatch):
    sid = sample["scenario"]["id"]
    a = client.post("/api/v1/simulations", json={"scenario_id": sid, "method": "fixed_schedule", "seed": 1}, headers={"Idempotency-Key": "abc"}).json()
    b = client.post("/api/v1/simulations", json={"scenario_id": sid, "method": "fixed_schedule", "seed": 1}, headers={"Idempotency-Key": "abc"}).json()
    assert a["id"] == b["id"]
    monkeypatch.setenv("IRRIVISE_MAX_QUEUED_JOBS", "1")
    from irrivise_api import config
    config.reset_settings_cache()
    r = client.post("/api/v1/simulations", json={"scenario_id": sid, "method": "fixed_schedule", "seed": 2})
    assert r.status_code == 429


def test_illegal_job_transition_rejected(client, sample):
    import pytest
    from irrivise_api.db.models import Job
    from irrivise_api.db.session import session_scope
    from irrivise_api.services import jobs
    j = client.post("/api/v1/simulations", json={"scenario_id": sample["scenario"]["id"], "method": "fixed_schedule"}).json()
    with session_scope() as s, pytest.raises(ValueError, match="Illegal"):
        jobs.transition(s, s.get(Job, j["id"]), "succeeded")


def test_exports_reconcile_with_saved_traces_and_reject_tampering(client, sample):
    sid = sample["scenario"]["id"]
    job = client.post("/api/v1/simulations", json={"scenario_id": sid, "method": "soil_threshold", "aquacrop": False}).json()
    run_next_job()
    run_id = client.get(f"/api/v1/jobs/{job['id']}").json()["result"]["run_id"]
    exp = client.post("/api/v1/exports", json={"source_type": "run", "source_id": run_id, "format": "zip"})
    assert exp.status_code == 201
    blob = client.get(exp.json()["download_url"])
    assert blob.status_code == 200
    with zipfile.ZipFile(io.BytesIO(blob.content)) as z:
        names = set(z.namelist())
        daily_csv = z.read("daily.csv").decode()
        manifest = z.read("manifest.json").decode()
    assert {"daily.csv", "decisions.json", "evaluation_truth.csv", "manifest.json", "report.html"} <= names
    total = sum(float(line.split(",")[list(daily_csv.splitlines()[0].split(",")).index("applied_mm")]) for line in daily_csv.splitlines()[1:])
    assert abs(total - client.get(f"/api/v1/simulations/{run_id}").json()["summary"]["seasonal_irrigation_mm"]) < 1e-6
    assert "weather_dataset_checksum" in manifest and "code_revision" in manifest
    html = client.post("/api/v1/exports", json={"source_type": "run", "source_id": run_id, "format": "html"}).json()
    page = client.get(html["download_url"]).text
    assert "<svg" in page and "not field measurements" in page
    # tamper with a saved artifact → export refused
    from irrivise_api.services import artifacts
    (artifacts.run_dir(run_id) / "daily.csv").write_text("tampered")
    r = client.post("/api/v1/exports", json={"source_type": "run", "source_id": run_id, "format": "csv"})
    assert r.status_code == 409 and r.json()["code"] == "artifact_modified"


def test_path_traversal_rejected(client):
    import pytest
    from irrivise_api.errors import ApiError
    from irrivise_api.services import artifacts
    assert client.get("/api/v1/exports/..%2F..%2Fetc%2Fpasswd").status_code in (400, 404)
    for bad in ("../etc", "..", "/abs"):
        with pytest.raises(ApiError):
            artifacts.safe_join("artifacts", bad)
    with pytest.raises(ApiError):
        artifacts.run_dir("../x")
