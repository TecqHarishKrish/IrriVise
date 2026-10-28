/** Plain-language definitions used by contextual tooltips and the Settings & Help glossary. */
export const GLOSSARY: Record<string, { term: string; text: string }> = {
  twin: { term: 'Digital twin', text: 'The system’s estimate of the field: an ensemble of plausible soil-water states with uncertainty. It never sees the simulated ground truth directly.' },
  reference: { term: 'Reference farm', text: 'A hidden simulation that plays the role of the real field. Only the sensor gateway (noisy, budgeted readings) and post-run evaluation can access it.' },
  ppo: { term: 'PPO', text: 'Proximal Policy Optimization — a reinforcement-learning algorithm. Here it learns an irrigation policy from simulated seasons.' },
  uncertainty: { term: 'Soil-water uncertainty', text: 'How much the plausible soil-water states disagree (ensemble spread). It grows between sensor readings and shrinks after a correction.' },
  regret: { term: 'Counterfactual regret (estimated)', text: 'Estimated possible loss from deciding with incomplete information: how much better each plausible state’s own best action would score than the action chosen under the belief. A model estimate, not a guarantee.' },
  voi: { term: 'Value of information (VOI)', text: 'How much a soil reading is expected to reduce estimated regret. Net VOI subtracts the reading cost and a budget shadow price. Observe only when net VOI exceeds the threshold.' },
  budget: { term: 'Observation budget', text: 'The number of simulated soil-moisture readings allowed per season. A reading is charged exactly once when it succeeds.' },
  proxy: { term: 'Yield proxy', text: 'An FAO-33 stage yield-response estimate from the fast simulator (t/ha scale). It is not measured yield and not AquaCrop output.' },
  aquacrop: { term: 'AquaCrop-simulated yield', text: 'Dry yield from replaying the applied irrigation schedule in AquaCrop-OSPy with default parameters. Simulated, not measured.' },
  wp: { term: 'Water productivity', text: 'Simulated yield per cubic metre of irrigation water (kg/m³). 1 mm over 1 ha = 10 m³.' },
  ks: { term: 'Water-stress coefficient Ks', text: 'FAO-56 factor from 1 (no stress) to 0 (no transpiration). Stress = 1 − Ks.' },
  taw: { term: 'TAW / RAW', text: 'Total and readily available water in the root zone (mm). Stress starts when depletion exceeds RAW = p × TAW.' },
  risk: { term: 'Risk manager', text: 'Hard limits (daily cap, seasonal water) are always enforced. A separate soft layer uses uncertain stress estimates to adjust actions and raise warnings.' },
  split: { term: 'Chronological split', text: 'Whole seasons are split in time order into train / validation / test. Models are tuned on train+validation only; test seasons are held out.' },
};
