# Fix-1 same-seed conditioning diff (NEW - OLD)
cutoff 2026-07-02T00:00:00Z n_sims 20000 posterior 9e5d4c66c9f99ac3 (cache hit, both sides)

- Algeria: reach_r16 0.433->0.398; reach_qf 0.125->0.113
- Belgium: reach_r16 0.644->0.622
- Canada: win_group 0.577->0.000; reach_r16 0.714->1.000; reach_qf 0.252->0.380; reach_sf 0.069->0.108; reach_final 0.022->0.035; first 0.577->0.000; second 0.423->1.000
- Czech Republic: advance_from_group 0.109->0.000; reach_r16 0.030->0.000; reach_qf 0.007->0.000; second 0.109->0.000; out 0.891->1.000
- Senegal: advance_from_group 0.891->1.000; reach_r16 0.337->0.378; reach_qf 0.197->0.225; reach_sf 0.050->0.059
- South Africa: reach_r16 0.119->0.000; reach_qf 0.027->0.000; second 0.891->1.000; third 0.109->0.000
- South Korea: third 0.891->1.000; out 0.109->0.000
- Switzerland: win_group 0.423->1.000; reach_r16 0.723->0.602; reach_qf 0.307->0.221; reach_sf 0.096->0.065; reach_final 0.034->0.025; first 0.423->1.000; second 0.577->0.000

CANARY Canada reach_r16 == 1.0: PASS (1.0000)
CANARY South Africa reach_r16 == 0.0: PASS (0.0000)
coherence: sum(champion)=1.000000 sum(reach_r16)=16.000000
