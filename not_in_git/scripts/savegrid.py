import json,glob,re
grid=[]
for f in sorted(glob.glob("g_aug_*.json"))+["none_val.json","mon_val.json"]:
    d=json.load(open(f)); c=d["cells"]; modes=["nominal","missing","biased+","biased-","stuck"]
    g=lambda mode,meth,k: c[f"{mode}|{meth}"]["mean"][k]
    m=re.fullmatch(r"g_aug_(\d+(?:\.\d+)?)_(\d+(?:\.\d+)?)\.json",f)
    entry={"method":"augmented" if m else ("none" if f.startswith("none") else "innovation_monitor"),
           "prior_std_m3m3":float(m.group(1)) if m else None,"drift_std_m3m3":float(m.group(2)) if m else None,
           "fault_mean_objective":round(sum(g(x,p,"reward") for x in modes for p in ["lookahead_carat","soil_threshold"])/10,4),
           "nominal_mean_objective":round((g("nominal","lookahead_carat","reward")+g("nominal","soil_threshold","reward"))/2,4),
           "end_of_season_offset_std_m3m3":round((float(m.group(1))**2+140*float(m.group(2))**2)**0.5,4) if m else None,
           "by_cell":{k:v["mean"] for k,v in c.items()}}
    grid.append(entry)
none=[e for e in grid if e["method"]=="none"][0]["nominal_mean_objective"]
out={"purpose":"Choose twin_bias prior/drift for the augmented offset state using VALIDATION seasons only (2016-2019).",
     "split":"validation","seeds":[1,2,3,4,5],"planners":["soil_threshold","lookahead_carat"],"faults":["nominal","missing","biased+","biased-","stuck"],
     "budget":10,"noise_m3m3":0.02,"objective":"objective_with_observation_cost (higher is better); by_cell keys use reward=objective, reads=observation_count, rmse=twin_rmse_mm, bias=twin_bias_mm",
     "selection_rule":"Highest fault-averaged objective among settings whose end-of-season offset std sqrt(prior^2 + 140*drift^2) is <= 0.05 m3/m3 and whose nominal objective is within 0.25 of method 'none'. Larger drifts scored higher only by letting the offset uncertainty grow until readings are effectively ignored.",
     "selected":{"prior_std_m3m3":0.015,"drift_std_m3m3":0.003},
     "note":"Generated with a working copy of scripts/sensor_bias_bench.py (same scenario, faults and planners) on the code committed as 'Add sensor-bias handling to the digital twin'. SIMULATED - not field data.",
     "grid":sorted(grid,key=lambda e:-e["fault_mean_objective"])}
open("/home/claude/irrivise/docs/results/sensor_bias_tuning.json","w").write(json.dumps(out,indent=1))
sel=[e for e in out["grid"] if e["method"]=="augmented" and e["end_of_season_offset_std_m3m3"]<=0.05 and e["nominal_mean_objective"]>=none-0.25]
print("selected by rule:",sel[0]["prior_std_m3m3"],sel[0]["drift_std_m3m3"],sel[0]["fault_mean_objective"], "n grid", len(grid))
