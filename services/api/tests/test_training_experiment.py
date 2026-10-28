"""PPO training through the worker, model registry, matched experiments and exports."""
from conftest import run_next_job


def test_quick_training_then_carat_simulation_and_experiment(client, sample):
    sid = sample["scenario"]["id"]
    r = client.post("/api/v1/training", json={"scenario_id": sid, "preset": "cpu_standard"})
    assert r.status_code == 422 and r.json()["code"] == "confirmation_required"
    assert client.post("/api/v1/training", json={"scenario_id": sid, "total_timesteps": 20000}).status_code == 422
    job = client.post("/api/v1/training", json={"scenario_id": sid, "total_timesteps": 512, "seeds": [3],
                                                "hyperparameters": {"n_steps": 256, "batch_size": 64}})
    assert job.status_code == 202 and job.json()["split"]["test"] == ["2020", "2021", "2022", "2023"]
    run_next_job()
    done = client.get(f"/api/v1/jobs/{job.json()['id']}").json()
    assert done["status"] == "succeeded", done["error"]
    model_id = done["result"]["selected_model_id"]
    model = client.get(f"/api/v1/models/{model_id}").json()
    assert model["selected"] and model["manifest"]["test_seasons_used"] == [] and model["actual_timesteps"] >= 512
    assert any(e["metric_name"] for e in client.get(f"/api/v1/jobs/{done['id']}/events?format=json").json()["events"])

    sim = client.post("/api/v1/simulations", json={"scenario_id": sid, "method": "carat_full", "model_id": model_id, "aquacrop": False}).json()
    run_next_job()
    sim_done = client.get(f"/api/v1/jobs/{sim['id']}").json()
    assert sim_done["status"] == "succeeded", sim_done["error"]
    run = client.get(f"/api/v1/simulations/{sim_done['result']['run_id']}").json()
    assert run["manifest"]["model_checkpoint_sha256"] == model["checkpoint_sha256"]

    exp = client.post("/api/v1/experiments", json={"scenario_id": sid, "model_id": model_id, "name": "Small matched test",
                                                   "methods": ["fixed_schedule", "ppo", "carat_full"], "reference_method": "ppo", "seeds": [1, 2]})
    assert exp.status_code == 202 and exp.json()["planned_runs"] == 24
    run_next_job()
    detail = client.get(f"/api/v1/experiments/{exp.json()['id']}").json()
    assert detail["status"] == "succeeded", detail["error"]
    assert detail["summary"]["n_runs"] == 24 and detail["summary"]["hard_constraint_violations"] == 0
    assert detail["manifest"]["evaluation_seasons"] == ["2020", "2021", "2022", "2023"]
    results = client.get(f"/api/v1/experiments/{exp.json()['id']}/results").json()
    assert results["total"] == 24 and isinstance(results["rows"][0]["season_id"], str)
    html = client.post("/api/v1/exports", json={"source_type": "experiment", "source_id": exp.json()["id"], "format": "html"}).json()
    assert "What did the data show?" in client.get(html["download_url"]).text
    assert client.post("/api/v1/exports", json={"source_type": "model", "source_id": model_id, "format": "zip"}).status_code == 201


def test_experiment_validation(client, sample):
    sid = sample["scenario"]["id"]
    r = client.post("/api/v1/experiments", json={"scenario_id": sid, "methods": ["ppo", "fixed_schedule"]})
    assert r.status_code == 422 and r.json()["code"] == "model_required"
    r = client.post("/api/v1/experiments", json={"scenario_id": sid, "methods": ["fixed_schedule"], "reference_method": "ppo"})
    assert r.status_code == 422
    r = client.post("/api/v1/experiments", json={"scenario_id": sid, "methods": ["nonsense"]})
    assert r.status_code == 422
