# Alpha research assistant: operating guide for Claude

This repo is a workspace for researching WorldQuant BRAIN alphas **interactively in
chat**. There is no Claude API key and no BRAIN API access:

- Claude proposes alphas and checks them locally with `python -m alphagen ...`
  (standard library only, nothing to install).
- The user runs them on the BRAIN website and pastes the results back.
- Claude logs the results, diagnoses them, and proposes the next round.

## Files

| Path | Purpose |
|---|---|
| `alphagen/` | Local tools: validator, journal, diagnosis, mutation, similarity, fitness math |
| `alphagen/data/operators.json` | Operator signatures the validator checks against |
| `alphagen/data/fields.json` | Known data fields (add new ones with `fields add`) |
| `alphagen/data/themes.json` | Research themes with hypotheses, citations and seed expressions |
| `knowledge/brain-platform.md` | Settings, Fitness, submission checks, syntax rules |
| `knowledge/correlation-playbook.md` | How to break self-correlation |
| `knowledge/research-principles.md` | Multiple testing, which anomalies replicate, BAB caveats, references |
| `journal/alphas.jsonl` | Every alpha tried, its settings and results (source of truth) |
| `journal/LESSONS.md` | Distilled lessons: read before proposing, update after diagnosing |

## Commands

```
python -m alphagen validate "<expr>" [--neutralization X --decay N]
python -m alphagen propose  "<expr>" --theme <id> --hypothesis "<one line>" [--decay N --neutralization X --universe U] [--parent A0003 --origin mutation]
python -m alphagen log A0007 --text "<pasted BRAIN results>"     # or --sharpe/--turnover/--fitness/--returns/... --self-corr --fail CHECK
python -m alphagen rerun A0007 --decay 6                          # same expression, new settings, new entry
python -m alphagen diagnose A0007 | show A0007 | list | top | stats
python -m alphagen status A0007 submitted                         # after the user submits on BRAIN
python -m alphagen mutate A0007 [--kind ...] | crossover A0003 A0007
python -m alphagen similar "<expr>" --submitted                   # self-correlation early warning
python -m alphagen fitness --sharpe 1.4 --returns 9% --turnover 35%
python -m alphagen themes [id] | operators [name] | fields search <q> | fields add <id> --kind vector ...
```

Skills in `.claude/skills/` cover the three recurring jobs: `new-alphas`,
`log-results`, `improve-alpha`.

## How a research round goes

1. **Orient.** Read `journal/LESSONS.md` and run `python -m alphagen stats` and
   `python -m alphagen list --status submitted` so you know what's been tried and what's
   in the portfolio.
2. **Hypothesize.** Pick a theme (`themes`) the portfolio lacks. State the hypothesis in
   one sentence before writing any expression.
3. **Write and check.** Draft the expression, run `propose` (it validates, dedupes,
   checks structural similarity against submitted alphas, and saves it). Fix every
   error. Read the warnings and act on them or say why not.
4. **Hand over.** Give the user a short block per alpha: the journal ID, the
   expression in a code block, and the settings table. Two or three alphas per round,
   each structurally different.
5. **Log and diagnose.** When results come back, `log` each one (the user's pasted text
   can go straight into `--text`). Explain the verdict in plain words and propose the
   next concrete simulations (decay ladder, decorrelation pivot, flip, drop).
6. **Learn.** Add lessons that generalize to `journal/LESSONS.md` (one line each, under
   the matching heading). Don't add one-off noise.
7. **Persist.** The session container is temporary. At the end of a round, commit
   `journal/` (and any field or theme additions) and push to the working branch.

## Rules

- Never claim an alpha passes or show metrics the user hasn't pasted. You can't run
  BRAIN. The only exception is predictable algebra: flipping the sign mirrors Sharpe and
  Fitness exactly.
- Every expression shown to the user must have passed `validate` or `propose`. Show the
  canonical form the tool prints.
- Every alpha needs a one-line economic hypothesis and a theme. No story, no simulation.
- Don't fix self-correlation by nudging parameters. Use
  `knowledge/correlation-playbook.md`.
- Count trials honestly: every simulated variant goes in the journal. Check the
  multiple-testing hurdle in `stats` before calling something robust.
- Fundamentals are compared within peers (`group_*` by industry/subindustry, or that
  neutralization). Vector fields get `vec_*` first. Lookbacks are integer constants.
- Low-volatility / beta ideas: TOP1000 or smaller, heavy decay, subindustry
  neutralization (see the BAB section of `knowledge/research-principles.md`).
- If the user only wants a quick alpha, answer directly with expression and settings.
  The full journal workflow is for when they're doing research rounds.
