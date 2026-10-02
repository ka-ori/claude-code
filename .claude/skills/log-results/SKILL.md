---
name: log-results
description: Record WorldQuant BRAIN simulation results the user pasted (Sharpe, Turnover, Fitness, Returns, Drawdown, Margin, failed checks, self-correlation), diagnose them and propose the next simulations. Use whenever the user pastes BRAIN metrics or says how an alpha did.
---

# Log results

1. **Match results to journal entries.** If the user doesn't give IDs, match by order
   or expression against `python -m alphagen list --limit 10`. Ask if unsure. If the
   alpha isn't in the journal (e.g. one the user wrote), `propose` it first with the
   settings they used.
   If the user ran it with different settings than the entry, use
   `python -m alphagen rerun <ID> --decay N ...` to create the right entry first, or pass
   `--settings-json`.
2. **Log each result.** Pass the pasted text through unchanged:
   `python -m alphagen log <ID> --text "<pasted results>"`.
   Add `--self-corr X` and `--fail CHECK_NAME` for anything the user reports from the
   submission checks. If the tool warns that pasted Fitness doesn't match
   Sharpe/Returns/Turnover, ask the user to double-check before continuing.
3. **Explain the verdict** in two or three plain sentences. What the numbers say about
   the hypothesis matters more than the threshold list.
4. **Propose the next simulations** (two or three, most promising first), using the tool's
   suggested actions as raw material:
   - `HIGH_TURNOVER`: decay ladder via `rerun --decay N`, or the gated variant
   - `NEAR_MISS`: neutralization change, group operator, or a complementary signal
   - `INVERTED`: flipping mirrors the metrics exactly (Sharpe -0.9 becomes +0.9), so
     only flip when the mirrored numbers pass and the reversed story makes sense;
     otherwise rethink what the signal is really picking up
   - `SELF_CORRELATED`: follow `knowledge/correlation-playbook.md` in order
   - `WEAK`: drop it and say why, then suggest a different theme or dataset
   - `PASS` / `PASS_UNPROVEN`: remind them to run BRAIN's submission check, then
     `python -m alphagen status <ID> submitted` once submitted
   Save each new candidate with `propose` (`--parent <ID> --origin mutation|decorrelate|flip`)
   or `rerun`, and hand them over in the usual format.
5. **Lessons.** If the result teaches something general (a field's sign, a theme that's
   crowded, the turnover a family needs), add one line to `journal/LESSONS.md` under the
   matching heading.
6. **Persist.** Commit `journal/` and push to the working branch at the end of the round.
