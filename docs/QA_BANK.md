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
unmet, it's relaxed for that interval and logged. In the stress week that happened in 22 intervals,
more than before lifeline because GridSetu now meets requests it used to miss.
We report the count rather than claim "never".

## Reliability Reserve confidence

**Q: Your reserve says 100% confidence. Is it ever wrong?**
On what it measures, no: across 1,260 published forecasts the feeder held its own evening peak
every time. The DISCOM's call is a separate promise, so it now has its own number: a firm call
capacity with a 90% confidence. When calls are bounded by our day-ahead offer, as in an ADMS
dispatch contract, the call was met on 58 of 60 evenings and the 90% held 97.6% of the time.

**Q: And if the DISCOM asks for more than you offered?**
That is how our model's DISCOM behaves today: it asks for the feeder's full share of the
shortage, a median 1.58 times our call capacity. Lifeline still met the call on 20 of 60
evenings; on the rest the feeder was switched off for part of the evening, with the clinic,
school and pump on the battery. We report both cases.

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
(2,204 vs 2,226 kWh in the stress week, the extra being energy served instead of shed). Split
across the three circuits, the same battery cuts technical losses about 7%, to 2,047 kWh. We
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

## Lifeline mode

**Q: What is lifeline?**
When the DISCOM needs more relief than the battery and flexible loads can give, a normal feeder
is switched off. GridSetu instead sets a load limit on every home's smart meter, as low as
200 W: lights, a fan, phone charging. The DISCOM gets its relief and the homes are not dark.
Over a month, home-hours without supply fall from 5,740 to 291.

**Q: Can smart meters really do that?**
Indian prepaid smart-meter specifications (for example MSEDCL's, which follows IS 16444)
already include a utility-set load limit with automatic disconnect and reconnect, and remote
connect/disconnect. Whether the limit can be changed remotely in real time is something we
still have to confirm with a DISCOM or meter vendor, and rationing would need the regulator's
approval. We say so.

**Q: Isn't 200 W an arbitrary number?**
It's our assumption, and it matters: at 400 W lifeline helps far less. A DISCOM and regulator
would set it. We show the sensitivity.

**Q: What happens to a home that uses more than 200 W?**
Its meter disconnects it, as prepaid meters already do when a load limit is exceeded. We assume
5% of limited homes do that, and count them as dark.

## Money

**Q: What does it cost, and who pays?**
About ₹7.0 lakh a year for one 420-home feeder, or ₹140 per home per month. Most of it is the
battery, priced from the 2025 Indian benchmark for 2-hour storage and doubled for small scale.
It pays for itself if an avoided outage is worth more than ₹21.8 per kWh. Diesel backup costs
about ₹33/kWh, so for anyone who would otherwise run a generator, it pays.

**Q: At ₹10/kWh it doesn't pay. Isn't that a problem?**
On energy value alone, no, it doesn't: benefit ÷ cost is 0.46 at the IEX ceiling. We say so.
The case rests on reliability: the clinic, school and pump never go dark, homes keep a lifeline
instead of a blackout, and the transformer stops tripping. Those are worth more than the
exchange price, which is why people buy diesel generators.

**Q: Doesn't the battery make money by buying cheap and selling dear?**
Not on this feeder. GridSetu serves more energy in the expensive evening than a feeder that is
switched off, so the average price paid per kWh stays the same (₹4.36 vs ₹4.35). We don't claim
arbitrage income.

**Q: What would make it cheaper?**
Battery price is the biggest lever: at utility-scale cost the break-even falls to about
₹15/kWh. Viability gap funding, pooling several feeders' batteries in one tender, or RDSS
funding for the smart plugs would all help.

## Household data

**Q: Is your household load realistic?**
Not per home, and we checked. Against 116 measured Indian homes (Prayas eMARC, public domain),
ours use 8.6 kWh a day against 4.6, and peak together far more. The Tamil Nadu
average is 3.5 kWh a day. What drives the results is the feeder's total demand, which is set
by its transformer. Spread the same demand over 720 or 1,030 lighter homes and GridSetu still cuts
evening unserved energy by about 80%, with the critical loads always on. Lifeline helps less,
and we show that.

**Q: Why not fix it?**
We're fitting the household model to the measured data next: real homes are spiky individually,
rarely peak together and have a morning peak. Until then we report both.
