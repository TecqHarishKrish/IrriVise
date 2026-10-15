"""Separate durable worker. One process claims one SQLite job at a time."""
import json
import hashlib
import time
from pathlib import Path
from irrivise_api.storage import ROOT, connect, ident, now, one
from irrivise_core.data import checksum, load_weather
from irrivise_core.science import Soil, simulate
from irrivise_core.aquacrop_adapter import evaluate_schedule
from irrivise_core.nasa_power import download_power
from datetime import date


def train_job(job: dict, scenario: dict) -> None:
    """Train quick PPO in the worker and persist only verified checkpoints."""
    from stable_baselines3 import PPO
    from stable_baselines3.common.callbacks import BaseCallback
    from stable_baselines3.common.env_checker import check_env
    from irrivise_core.ppo_env import IrrigationEnv

    weather_path = ROOT / "data/sample/weather.csv"
    env = IrrigationEnv(load_weather(weather_path), scenario["budget_mm"], scenario["daily_max_mm"])
    check_env(env)

    class Progress(BaseCallback):
        cancelled = False

        def _on_step(self) -> bool:
            if self.num_timesteps % 32:
                return True
            with connect() as db:
                item = one(db, "SELECT cancel_requested FROM jobs WHERE id=?", (job["id"],))
                if item["cancel_requested"]:
                    self.cancelled = True
                    return False
                db.execute("UPDATE jobs SET current_step=?,progress=? WHERE id=?", (self.num_timesteps, min(99, int(100 * self.num_timesteps / job["total_steps"])), job["id"]))
            return True

    callback = Progress()
    model = PPO("MlpPolicy", env, seed=job["seed"], n_steps=256, batch_size=64, learning_rate=3e-4, device="cpu", verbose=0)
    model.learn(total_timesteps=job["total_steps"], callback=callback)
    if callback.cancelled:
        with connect() as db:
            db.execute("UPDATE jobs SET status='cancelled',finished_at=? WHERE id=?", (now(), job["id"]))
        return
    directory = ROOT / "artifacts/models"
    directory.mkdir(parents=True, exist_ok=True)
    checkpoint = directory / f"{job['id']}.zip"
    model.save(str(checkpoint))
    loaded = PPO.load(str(checkpoint), env=env, device="cpu")
    observation, _ = env.reset(seed=job["seed"])
    action, _ = loaded.predict(observation, deterministic=True)
    _, reward, _, _, info = env.step(int(action))
    manifest = {"id": job["id"], "algorithm": "PPO", "preset": "cpu_quick", "scenario_id": job["scenario_id"], "dataset": "synthetic demonstration", "dataset_sha256": checksum(weather_path), "seed": job["seed"], "requested_timesteps": job["total_steps"], "actual_timesteps": model.num_timesteps, "checkpoint": str(checkpoint.relative_to(ROOT)), "checkpoint_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(), "inference_action_mm": info["applied_mm"], "inference_reward": reward, "research_quality": False, "evaluation": "save/load/one-step inference only"}
    (directory / f"{job['id']}.json").write_text(json.dumps(manifest, indent=2))
    with connect() as db:
        db.execute("UPDATE jobs SET status='succeeded',progress=100,current_step=?,finished_at=? WHERE id=?", (model.num_timesteps, now(), job["id"]))


def process_one() -> bool:
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        job = one(db, "SELECT * FROM jobs WHERE status='queued' ORDER BY created_at LIMIT 1")
        if not job:
            return False
        db.execute("UPDATE jobs SET status='running',started_at=? WHERE id=? AND status='queued'", (now(), job["id"]))
    try:
        with connect() as db:
            scenario = one(db, "SELECT * FROM scenarios WHERE id=?", (job["scenario_id"],))
        if job["kind"] == "training":
            train_job(job, scenario)
            return True
        if job["kind"] == "weather":
            payload = json.loads(job["payload_json"])
            manifest = download_power(payload["latitude"], payload["longitude"], date.fromisoformat(payload["start"]), date.fromisoformat(payload["end"]), payload["time_standard"], ROOT)
            with connect() as db:
                if one(db, "SELECT cancel_requested FROM jobs WHERE id=?", (job["id"],))["cancel_requested"]:
                    db.execute("UPDATE jobs SET status='cancelled',finished_at=? WHERE id=?", (now(), job["id"]))
                else:
                    db.execute("UPDATE jobs SET status='succeeded',progress=100,finished_at=?,dataset_id=? WHERE id=?", (now(), manifest["id"], job["id"]))
            return True
        simulation_payload = json.loads(job["payload_json"]) if job["payload_json"] else {"dataset_id": "sample"}
        dataset_id = simulation_payload["dataset_id"]
        weather_path = ROOT / "data/sample/weather.csv" if dataset_id == "sample" else ROOT / "data/processed" / f"nasa-{dataset_id}.csv"
        weather = load_weather(weather_path)
        trace, summary = simulate(weather, Soil(), scenario["budget_mm"], scenario["daily_max_mm"], scenario["observation_budget"], job["controller"], job["seed"])
        summary["aquacrop"] = evaluate_schedule(weather, [day["irrigation_mm"] for day in trace])
        summary["dataset_sha256"] = checksum(weather_path)
        summary["dataset_id"] = dataset_id
        summary["dataset_source"] = "synthetic demonstration" if dataset_id == "sample" else "NASA POWER historical weather"
        if dataset_id != "sample":
            summary["provenance"] = "NASA POWER historical gridded weather; simulated reference farm; yield proxy uncalibrated"
        summary["seed"] = job["seed"]
        with connect() as db:
            if one(db, "SELECT cancel_requested FROM jobs WHERE id=?", (job["id"],))["cancel_requested"]:
                db.execute("UPDATE jobs SET status='cancelled',finished_at=? WHERE id=?", (now(), job["id"]))
                return True
        run_id = ident()
        relative = Path("artifacts/runs") / f"{run_id}.json"
        path = ROOT / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(trace, indent=2))
        with connect() as db:
            db.execute("INSERT INTO runs(id,job_id,scenario_id,controller,summary_json,trace_path,created_at) VALUES (?,?,?,?,?,?,?)", (run_id, job["id"], job["scenario_id"], job["controller"], json.dumps(summary), str(relative), now()))
            db.execute("UPDATE jobs SET status='succeeded',progress=100,finished_at=?,run_id=? WHERE id=?", (now(), run_id, job["id"]))
    except Exception as exc:
        with connect() as db:
            db.execute("UPDATE jobs SET status='failed',error=?,finished_at=? WHERE id=?", (str(exc)[:500], now(), job["id"]))
    return True


def main() -> None:
    with connect() as db:
        db.execute("UPDATE jobs SET status='interrupted',error='Worker restarted before completion',finished_at=? WHERE status='running'", (now(),))
    while True:
        if not process_one():
            time.sleep(0.5)


if __name__ == "__main__":
    main()
