# Breaking self-correlation

BRAIN rejects a new alpha whose daily PnL correlates 0.7 or more with an alpha you have
already submitted. Nudging parameters (20 days to 21 days) barely changes the PnL. You
have to change **when**, **where**, or **from what** the alpha takes its bets.

`python -m alphagen mutate <ID> --kind <kind>` generates the mechanical versions below.
`python -m alphagen similar "<expr>" --submitted` gives a structural early warning
before you spend a simulation.

Work down the list. Each step is a bigger structural change than the one before it.

## 1. Event gating with `trade_when`  (kind: `volume_event_gate`)

```
trade_when(volume > ts_mean(volume, 20), ALPHA, -1)
```

The alpha only updates on abnormal-volume days and holds its position otherwise, which
gives a different equity curve. Other triggers:
- earnings or estimate updates: `days_from_last_change(field) < 5`
- large moves: `abs(returns) > 2 * ts_std_dev(returns, 20)`

## 2. Regime gating  (kinds: `turbulent_regime_gate`, `calm_regime_gate`)

```
trade_when(ts_std_dev(returns, 20) > ts_std_dev(returns, 60), ALPHA, -1)
```

Only active when short-term volatility is above (or below) its 60-day baseline.
A full regime switch combines two hypotheses:

```
if_else(ts_std_dev(returns, 20) > ts_std_dev(returns, 60), TREND_LEG, REVERSAL_LEG)
```

(`python -m alphagen crossover A B` builds this from two journal entries.)

## 3. Change the weight distribution  (kind: `normalizer_swap`)

`rank` gives uniform weights. `zscore` / `group_zscore` / `ts_zscore` follow magnitude
and overweight outliers. The hypothesis stays the same but the weights change. The
correlation drop is often modest, so combine this with another step.

## 4. Change the comparison set  (kinds: `group_change`, `group_neutralize`)

Comparing within subindustry vs sector vs market changes which bets survive
neutralization. Also try a different Neutralization setting with
`python -m alphagen rerun <ID> --neutralization INDUSTRY`.

## 5. Change the horizon class  (kind: `horizon_shift`)

Short (≤10 days), medium (≤63) and long (>63) horizons are largely separate return
streams. Moving a reversal idea from 5 days to 60 days is a structural change.
Moving from 5 to 6 days is not.

## 6. Same hypothesis, different data

Express the economic idea through another dataset. For example, the profitability story
can come from fundamentals, analyst estimates, or news sentiment. Different datasets give
different noise and timing, so the correlation drops the most. Look for fields with fewer
existing alphas (less crowded) on the BRAIN Data page.

## What doesn't work

- Small lookback changes, adding a constant, multiplying by -1 twice.
- Blending with the correlated alpha: `rank(A) + rank(B)` raises correlation with both.
