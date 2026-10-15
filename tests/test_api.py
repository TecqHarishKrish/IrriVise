from fastapi.testclient import TestClient
import pytest
import shutil
from irrivise_api.main import app
from irrivise_api import main as api_main
from irrivise_api import storage
from irrivise_api import worker
from irrivise_api import auth
from irrivise_api.worker import process_one


client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB", tmp_path / "test.sqlite3")
    sample = tmp_path / "data/sample/weather.csv"
    sample.parent.mkdir(parents=True)
    shutil.copy(storage.ROOT / "data/sample/weather.csv", sample)
    monkeypatch.setattr(worker, "ROOT", tmp_path)
    monkeypatch.setattr(api_main, "ROOT", tmp_path)
    with storage.connect() as db:
        db.execute("INSERT INTO accounts(id,email,role,created_at,last_seen_at) VALUES (?,?,?,?,?)", ("test-admin", "admin@example.test", "admin", storage.now(), storage.now()))
    app.dependency_overrides[auth.current_actor] = lambda: auth.Actor(id="test-admin", email="admin@example.test", role="admin")
    yield
    app.dependency_overrides.clear()


def test_offline_journey():
    assert client.get("/health").status_code == 200
    project = client.post("/api/v1/projects", json={"name": "Test field", "crop": "maize"}).json()
    scenario = client.post(f"/api/v1/projects/{project['id']}/scenarios", json={"name": "Test season", "budget_mm": 50, "daily_max_mm": 10, "observation_budget": 2}).json()
    response = client.post("/api/v1/simulations", json={"scenario_id": scenario["id"], "controller": "carat", "seed": 42})
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    assert process_one()
    job = client.get(f"/api/v1/jobs/{job_id}").json()
    assert job["status"] == "succeeded"
    run = client.get(f"/api/v1/simulations/{job['run_id']}").json()
    days = client.get(f"/api/v1/simulations/{run['id']}/daily").json()
    evaluation = client.get(f"/api/v1/simulations/{run['id']}/evaluation").json()
    assert len(days) == 150
    assert "reference_storage_mm_evaluation_only" not in days[0]
    assert "reference_storage_mm_evaluation_only" in evaluation[0]
    assert sum(day["irrigation_mm"] for day in days) == run["summary"]["seasonal_irrigation_mm"]
    assert run["summary"]["seasonal_irrigation_mm"] <= 50
    assert run["summary"]["observations_used"] <= 2
    assert run["summary"]["aquacrop"]["aquacrop_simulated_dry_yield_t_ha"] >= 0


def test_invalid_input_and_unknown_id():
    assert client.get("/api/v1/scenarios/unknown").status_code == 404
    assert client.post("/api/v1/projects", json={"name": "x", "crop": "maize"}).status_code == 422


def test_training_worker_save_load():
    project = client.post("/api/v1/projects", json={"name": "Training field", "crop": "maize"}).json()
    scenario = client.post(f"/api/v1/projects/{project['id']}/scenarios", json={"name": "Training season", "budget_mm": 100, "daily_max_mm": 20, "observation_budget": 0}).json()
    response = client.post("/api/v1/training", json={"scenario_id": scenario["id"], "total_timesteps": 256, "seed": 7})
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    assert process_one()
    job = client.get(f"/api/v1/jobs/{job_id}").json()
    assert job["status"] == "succeeded", job["error"]
    assert job["current_step"] == 256
    assert any(model.get("id") == job_id for model in client.get("/api/v1/models").json())


def test_weather_job_is_durable(tmp_path, monkeypatch):
    project = client.post("/api/v1/projects", json={"name": "Weather field", "crop": "maize"}).json()
    scenario = client.post(f"/api/v1/projects/{project['id']}/scenarios", json={"name": "Weather season", "budget_mm": 100, "daily_max_mm": 20, "observation_budget": 0}).json()
    response = client.post("/api/v1/datasets/nasa-power", json={"scenario_id": scenario["id"], "latitude": 10.79, "longitude": 78.7, "start": "2024-01-01", "end": "2024-01-07", "time_standard": "UTC"})
    assert response.status_code == 202
    def fake_download(latitude, longitude, start, end, time_standard, root):
        path = root / "data/manifests/nasa-test.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"id":"test","source":"nasa_power","days":7,"start":"2024-01-01","end":"2024-01-07","checksum_sha256":"abc"}')
        return {"id": "test"}
    monkeypatch.setattr(worker, "download_power", fake_download)
    assert process_one()
    job = client.get(f"/api/v1/jobs/{response.json()['job_id']}").json()
    assert job["status"] == "succeeded"
    assert job["dataset_id"] == "test"
    assert any(item["id"] == "test" for item in client.get("/api/v1/datasets").json())
