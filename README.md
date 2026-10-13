# IrriVise — Intelligent Irrigation Through Digital Twin and Reinforcement Learning

**Tagline: Think Before You Water.**

IrriVise is an AI-powered smart irrigation research framework designed to improve agricultural water management through Digital Twin technology, Reinforcement Learning, and decision-aware environmental sensing.

The system creates a virtual agricultural field that simulates soil moisture, weather conditions, crop growth stages, and irrigation requirements. A Reinforcement Learning agent learns adaptive irrigation strategies to determine when crops require water and how much irrigation should be applied.

At its core, IrriVise incorporates the proposed **CARAT (Counterfactual Action-Regret and Adaptive Twin Correction)** algorithm, which evaluates how uncertain environmental information could affect irrigation decisions.

Rather than depending on continuous soil measurements or fixed observation intervals, the system estimates whether obtaining updated soil information would meaningfully improve the current irrigation decision. When additional information is valuable, the Digital Twin updates its estimated state before the system recommends an irrigation action.

The framework also evaluates crop-water stress, irrigation limits, and environmental uncertainties to support more reliable and resource-efficient decisions.

**Core Technologies:** Python, AquaCrop-OSPy, Gymnasium, PPO Reinforcement Learning, NumPy, Pandas, SciPy, and Streamlit.

**Research Goal:** To investigate whether decision-aware observation scheduling and counterfactual regret estimation can improve irrigation water efficiency, crop productivity, and decision reliability compared with conventional irrigation and existing RL-based approaches.

IrriVise is developed as a fully software-based research system using open-source technologies and freely available environmental datasets, without requiring physical sensors, agricultural equipment, or paid APIs.
