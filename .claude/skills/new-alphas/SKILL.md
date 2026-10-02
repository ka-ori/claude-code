---
name: new-alphas
description: Generate new WorldQuant BRAIN alpha ideas grounded in a research theme, validate them locally and hand the user copy-paste expressions with settings. Use when the user asks for new alphas, ideas, a research round, or alphas on a specific theme or dataset.
---

# New alphas

1. **Orient** (skip if done earlier in this conversation):
   - read `journal/LESSONS.md`
   - `python -m alphagen stats` and `python -m alphagen list --status submitted`
2. **Choose themes.** If the user named one, use it. Otherwise
   `python -m alphagen themes` and pick themes that are missing or under-explored in
   the portfolio. Prefer the JKP clusters (`knowledge/research-principles.md`). Read the
   theme: `python -m alphagen themes <id>`.
3. **Fields.** `python -m alphagen fields search <words>` for what's known. If the
   idea needs a field that isn't listed, ask the user for the exact ID and type
   (matrix/vector) from the BRAIN Data page, then `python -m alphagen fields add`.
4. **Write 2-3 alphas** that are structurally different from each other (different
   data, horizon, or gating), not lookback variants. For each:
   - one-sentence hypothesis: who is wrong or what risk is paid, and why it persists
   - start from the theme's seeds or settings, then adapt to the lessons
   - `python -m alphagen propose "<expr>" --theme <id> --hypothesis "<...>"` plus any
     settings flags. Fix every error. For each warning, change the expression or say
     why it stays.
   - if `propose` reports high similarity to a submitted alpha, restructure it using
     `knowledge/correlation-playbook.md` before showing it
5. **Hand over**, per alpha:

   ````
   **A0012**: <hypothesis>
   ```
   <canonical expression from propose>
   ```
   Region USA · Universe TOP3000 · Delay 1 · Decay 0 · Neutralization Subindustry · Truncation 0.08 · Pasteurization On · Unit Handling Verify · NaN Handling Off
   ````

   Then one line: "Paste the results (Sharpe, Turnover, Fitness, Returns, Drawdown,
   Margin, and any failed checks) and I'll log and diagnose them."

Rules: never predict metrics; never show an expression that didn't pass `propose`;
keep expressions as simple as the hypothesis allows.
