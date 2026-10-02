---
name: improve-alpha
description: Improve an existing WorldQuant BRAIN alpha - fix low fitness, high or low turnover, self-correlation, or evolve the best alphas through mutation and crossover. Use when the user asks to fix, improve, decorrelate, evolve or combine alphas.
---

# Improve an alpha

1. **Load the context:** `python -m alphagen show <ID>` and `python -m alphagen diagnose <ID>`.
   For "improve my best ones": `python -m alphagen top --n 5`.
2. **Pick the move that fits the verdict:**

   | Problem | Move |
   |---|---|
   | Turnover too high / fitness dragged by turnover | `rerun <ID> --decay N` up the ladder 0→2→4→6→8→10→15→20, or `mutate <ID> --kind volume_event_gate --kind decay_wrap` |
   | Turnover < 1% | lower decay; add a faster component (`mutate --kind lookback`) |
   | Sharpe near the bar | `rerun --neutralization ...`, `mutate --kind group_change --kind group_neutralize`, or `crossover` with a strong alpha from a different theme |
   | Self-correlation | `knowledge/correlation-playbook.md` in order; `mutate --kind volume_event_gate --kind turbulent_regime_gate --kind calm_regime_gate --kind normalizer_swap --kind horizon_shift`; check `similar "<expr>" --submitted` before handing over |
   | Concentrated weights | wrap in `rank` / `winsorize(x, std=4)`, `rerun --truncation 0.05` |

3. **Add judgment the tools lack.** The mechanical variants are a starting point.
   Also consider semantic changes: the same hypothesis on a different dataset,
   conditioning on a regime where the story should be strongest, or a crossover where one
   alpha gates the other (`crossover A B` prints regime-switch and gate templates).
4. **Limit the batch.** Pick at most three variants per round, each changing one thing,
   so the results are attributable. Every variant is a trial for the multiple-testing
   hurdle (`stats`).
5. **Save and hand over:** `propose "<expr>" --parent <ID> --origin mutation|crossover|decorrelate`
   (or `rerun` for settings-only changes), then show ID, expression and settings as in
   `new-alphas`.
