# alphagen: WorldQuant BRAIN alpha research with Claude

A workspace for researching [WorldQuant BRAIN](https://platform.worldquantbrain.com)
alphas by chatting with Claude in the Claude app or Claude Code. You don't need a Claude
API key or BRAIN API access: Claude writes and checks the alphas, you run them on the BRAIN
website, and paste the results back.

```
you: "give me 3 new alphas, something we haven't tried"
Claude: picks themes from the literature, writes expressions, validates them locally,
        logs them as A0012-A0014, hands you expression + settings
you: run them on BRAIN, paste the numbers back
Claude: logs them, diagnoses (turnover? correlation? wrong sign?), proposes the next round
```

## What's inside

- **Fast Expression validator** (`alphagen/fastexpr/`). Parses expressions with Python's
  `ast` module and checks them against an operator registry before you spend a
  simulation. It catches unknown operators, wrong argument counts, vector fields not
  collapsed with `vec_*`, non-group arguments to `group_*`, non-constant or oversized
  lookbacks, and Python-only syntax. It also warns about research mistakes: raw price
  levels, fundamentals compared across sectors, unsmoothed short-horizon signals, and
  overly complex expressions.
- **Journal** (`journal/alphas.jsonl`). Every alpha, its settings, its pasted results,
  and its lineage (parent → mutation → decay re-run).
- **Diagnosis**. Turns results into a verdict (HIGH_TURNOVER, NEAR_MISS, INVERTED,
  SELF_CORRELATED, WEAK, PASS, ...) and concrete next simulations: the decay ladder, a
  neutralization sweep, event or regime gating, and decorrelation pivots.
- **Mutation and crossover**. Mechanical, validated variants: lookback jumps, rank↔zscore
  swaps, group changes, `trade_when` volume/volatility gates, regime-switch crossovers.
- **Self-correlation early warning**. A structural similarity score against submitted
  alphas (BRAIN's real check uses PnL, which only BRAIN has).
- **Research grounding** (`knowledge/`, `alphagen/data/themes.json`). Themes drawn from
  replicated asset-pricing evidence (Jensen-Kelly-Pedersen clusters, the q-factor
  model, gross profitability, and others), the Harvey-Liu-Zhu multiple-testing hurdle,
  and the caveats on Betting Against Beta.
- **Claude Code setup**. `CLAUDE.md` is the operating guide, and `.claude/skills/` holds
  three skills: `new-alphas`, `log-results`, `improve-alpha`.

## Using it

Open this repo in Claude Code (desktop app, web, or terminal) and talk normally:

- "Give me two alphas on profitability and one on short-term reversal."
- "Here are the results for A0003: Sharpe 1.41, Turnover 48%, Fitness 0.83, ..."
- "A0007 fails self-correlation at 0.82, fix it."
- "Evolve my best three alphas."

Claude runs the tools itself. You can also run them directly (Python 3.10+, no
dependencies):

```
python -m alphagen validate "group_rank((revenue - cogs) / assets, sector)"
python -m alphagen propose  "group_rank((revenue - cogs) / assets, sector)" --theme gross_profitability --hypothesis "productive firms are underpriced"
python -m alphagen log A0001 --text "Sharpe 1.41 Turnover 4.2% Fitness 1.02 Returns 6.1% Drawdown 5% Margin 29"
python -m alphagen rerun A0001 --neutralization INDUSTRY
python -m alphagen mutate A0001
python -m alphagen stats
python -m alphagen themes
python -m alphagen operators group_mean
python -m alphagen fields add my_vector_field --kind vector --category news --description "..."
python -m alphagen fitness --sharpe 1.4 --returns 9% --turnover 35%
```

## Keeping the field list current

`alphagen/data/fields.json` ships with common USA price-volume and fundamental fields.
Field IDs differ by region, delay and dataset, so when you use a new dataset, copy the
field ID and type (matrix or vector) from the BRAIN Data page and add it with
`fields add`, or ask Claude to. Validate with `--strict-fields` to treat unknown fields as
errors.

If BRAIN rejects an operator your account doesn't have, add `"unavailable": true` to its
entry in `alphagen/data/operators.json`.

## Persistence

Claude cloud sessions run in a temporary container. The journal lives in git, so commit
and push `journal/` at the end of each research round (Claude does this as part of the
workflow).

## Tests

```
pip install pytest && python -m pytest
```

The tests cover the validator, the canonical printer, fitness and multiple-testing math,
mutations, the journal workflow, and that every theme seed validates against the field
dictionary.
