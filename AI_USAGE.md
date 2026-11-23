# How AI tools were used

We used AI assistants (Anthropic's Claude) during development, for drafting code,
documentation and figures, and for reviewing our own work. The Yuva Yodha terms ask that
no *unauthorized* AI-generated content is submitted; this note is our disclosure.

## Our rules

1. **No AI-invented numbers.** Every figure in the README, deck and submission comes from
   code anyone can re-run (`outputs/numbers.json` lists each figure and where it comes from)
   or from a cited public source with a date. The operator copilot follows the same rule: it
   answers only from simulator tool calls.
2. **A team member reviews every change** before it is merged, through a pull request.
3. **We can explain it.** Every significant module has a plain-language explanation in
   [`docs/TEAM_BRIEF.md`](docs/TEAM_BRIEF.md). If no one on the team can explain a piece of
   code, it does not ship.
4. **Checks a tool cannot fake.** Tests (`pytest -q`), the README figure check and full
   reproduction (`scripts/reproduce.sh`) run in CI on every pull request.
