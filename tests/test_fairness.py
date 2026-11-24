import numpy as np

from gridsetu.fairness import FairnessLedger


def test_gini_counts_only_homes_with_load_to_shift():
    led = FairnessLedger(4, 0.0, np.random.default_rng(0))
    tier3 = np.array([1.0, 1.0, 0.0, 0.0])          # two homes have nothing to pause
    for _ in range(4):
        led.step(1.0, tier3, 0.25)
    s = led.summary()
    assert s["households_with_shiftable_load"] == 2
    assert s["households_ever_curtailed"] == 2
    assert s["gini_curtailment_hours"] == 0.0        # the two able homes shared it evenly
    assert s["gini_all_homes"] > 0.4                 # counting idle homes would call it unfair
