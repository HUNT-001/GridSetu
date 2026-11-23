# Hard questions and our answers

The questions a Schneider grid engineer, a DISCOM CFO or a judge is most likely to ask, with
answers we can back with evidence. Keep answers short enough to say aloud in 30 seconds.

## Trust in the numbers

**Q: How do we know your numbers aren't tuned to look good?**
Every headline figure is in `outputs/numbers.json` with the exact path it comes from in
`results.json`. `scripts/reproduce.sh` re-runs the whole study from scratch and fails if a single
value changes, and CI runs it on every pull request. We also publish results that went against
us: the solar-utilisation claim we dropped, and the 30-hour shortfall GridSetu can't fully cover.

**Q: If I install it myself, will I get your numbers?**
With `requirements-lock.txt`, yes, exactly. With loose versions the headline figures move by 1–3%
because solver and ML library versions differ, but every percentage change stays the same. We
found this ourselves and pinned the versions.

**Q: "Never the same home twice in a row": is that true?**
Almost. The rule is enforced inside dispatch, but if honouring it would leave the DISCOM's request
unmet, it's relaxed for that interval and logged. In the stress week that happened in 4 intervals.
We report the count rather than claim "never".

## Reliability Reserve confidence

**Q: Your reserve says 100% confidence. Is it ever wrong?**
On what it measures, no: across 1,260 published forecasts the feeder held its own evening peak
every time. But on the 60 evenings when the DISCOM called for relief, it asked for 1.2 to 4.3
times what we had published, and we could not meet it. The feeder was rotated off like its
neighbours, with the clinic, school and pump on battery. We show both numbers, and we're adding
a second confidence for the expected call.

**Q: Why would the DISCOM ask for more than you offered?**
In our model the DISCOM shares the shortfall across feeders by their load, not by what each one
published. In a real ADMS/DERMS integration the published reserve is what the operator dispatches
against, so calls should be bounded by it. That change is next.

**Q: Then what's the value on the worst nights?**
Critical loads never go dark, and GridSetu is honest about what it can't do, so the operator can
plan the rest of the shed. A feeder that over-promises is worse than one that says "twice that is
beyond me".

## The MATLAB model

**Q: Why a second model in MATLAB?**
The Python simulator treats the feeder as one point, so it can't see losses or voltage along the
wires. The MATLAB model runs a load flow on the low-voltage network with exactly the same loads.
Where the two overlap (transformer loading) they must agree, and that agreement is checked.

**Q: Where do the bus loads come from?**
From `python -m gridsetu export-matlab`. Each home, enterprise and critical load is placed on a
named bus; a test proves the bus loads add up to the feeder import at every step.

**Q: Does GridSetu reduce technical losses?**
Only where the storage sits. With the battery at the transformer, line losses are unchanged
(2,204 vs 2,215 kWh in the stress week, the extra being energy served instead of shed). Split
across the three circuits, the same battery cuts technical losses about 7%, to 2,042 kWh. We
now recommend the split layout.

**Q: What does it do for the transformer?**
Peak loading falls from 1.37 to 1.19 pu and the hot-spot peak by about 9 °C (IEC 60076-7 model).
In this IS 1180 Level-2 unit ageing is already low in absolute terms, so the real benefit is
fewer overload trips and headroom, not years of life.

**Q: Where do your network parameters come from?**
`matlab/f07_params.json`: transformer data from a DISCOM specification to IS 1180 Level 2,
conductor resistance from a manufacturer's ACSR datasheet, and every assumption (lengths,
spacing, power factor, voltage limit) marked as one.

## Real data

**Q: Is any of this real data?**
Weather and exchange prices, yes. NASA POWER sunshine and temperature for Coimbatore, and IEX
day-ahead prices for the same September week in 2025. Household load is still synthetic. Every
input is labelled REAL, DERIVED, SOURCED or SYNTHETIC in `docs/DATA_CARD.md`.

**Q: Does GridSetu still work on real weather?**
Yes. On the real week the critical loads stayed powered and evening unserved energy fell from
808 to 408 kWh, a bigger cut than in our synthetic week. That's because our synthetic stress
week forces two overcast days and the real week had none, so we kept the harsher synthetic
week for the headline.

**Q: Your price assumptions?**
Real prices are more extreme than ours. In the real week the evening price hit the ₹10/kWh
ceiling on 6 of 7 days; our curve peaks at ₹9.8. Real midday power averaged ₹1.17/kWh against
our ₹2.6. A battery that charges at midday and serves the evening is worth more than we
assumed.

**Q: How good is the forecast on real weather?**
Backtested on three real weeks with only yesterday's weather as the weather forecast, the
actual load fell inside our 80% range 79% of the time. On synthetic weather it was 85%, so
the synthetic number was slightly flattering, and we report the real one.

**Q: How did you get the IEX data?**
From IEX's public market snapshot page, 15-minute blocks. Each day's 96 prices average exactly
to IEX's published daily figure, and a test checks it.
