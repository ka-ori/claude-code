# Research principles

How to tell real alphas from noise. These rules apply every time an alpha is proposed.

## 1. Every alpha starts from an economic story

Write the hypothesis in one sentence: who is making a mistake, or what risk is being
paid for, and why prices adjust slowly. Then pick the fields and operators that express
it. An expression without a story is a data-mining artifact even if its Sharpe is high.
`alphagen/data/themes.json` lists documented starting points.

## 2. Multiple testing: the hurdle rises with every try

Harvey, Liu & Zhu (2016) argue that after hundreds of published factors, a new one needs
t > 3.0, not 2.0. The same logic applies to a personal search. Every alpha you simulate is
a trial, so the bar keeps rising:

- `python -m alphagen stats` prints the Bonferroni-adjusted t hurdle for the number of
  simulated alphas in the journal (never below 3.0).
- A Sharpe *S* over a *Y*-year in-sample window has t ≈ S·√Y. With 5 years, Sharpe 1.25
  is t ≈ 2.8, just below the HLZ bar.
- Prefer one robust alpha with a clear story over five fragile variants of a lucky one.
  When an alpha only works at one lookback, one neutralization and one universe, it is
  probably overfit.

## 3. Respect the evidence on which anomalies replicate

- **Jensen, Kelly & Pedersen (2023)** find most factors replicate once grouped into 13
  themes: accruals, debt issuance, investment, leverage, low risk, momentum, profit
  growth, profitability, quality, seasonality, short-term reversal, size, value. They
  are a good map of where real premia live.
- **Hou, Xue & Zhang (2015, 2020)**: the investment-based q-factor model (investment and
  profitability) explains many anomalies; most of the 452 anomalies they re-test are
  insignificant once micro-caps are handled properly. Liquid universes matter.
- **Novy-Marx (2013)**: gross profits / assets predicts returns about as well as
  book-to-market. Write it `(revenue - cogs) / assets`. Without the parentheses,
  `revenue - cogs / assets` divides only cogs.

## 4. Betting Against Beta needs care

Frazzini & Pedersen (2014): leverage-constrained investors overpay for high-beta stocks,
so low-beta stocks earn higher risk-adjusted returns. Novy-Marx & Velikov (2022) show that
much of BAB's reported performance comes from its rank-weighting, which concentrates in
small, illiquid stocks, and from non-standard beta estimation. With conventional weights
and trading costs, most of it disappears. On BRAIN:

- run low-risk ideas on TOP1000/TOP500, not the TOP3000 tail;
- smooth heavily (Decay 10+), since volatility sorts churn;
- neutralize by subindustry so it isn't just an industry or profitability bet;
- a refinement in the spirit of Campbell & Vuolteenaho (2004), whose "bad beta" is
  exposure to cash-flow news: short high-volatility stocks whose cash flows are
  deteriorating instead of high-volatility stocks in general.

## 5. Use relationships between companies

Some datasets map supply chains, subsidiaries and partnerships. Treat the links as
directional economic channels, in the spirit of the EDM Council's Financial Industry
Business Ontology (FIBO):

| Relationship | Direction of information | How to express it |
|---|---|---|
| customer → supplier | customer news reaches suppliers with a lag (Cohen & Frazzini 2008) | `group_mean(signal, 1, customer_group) - signal` |
| parent → subsidiary | shared ownership: shocks propagate fast | neutralize within the ownership group |
| competitors (same subindustry) | relative performance; zero-sum share shifts | `group_rank` / `group_neutralize` by subindustry |

Relationship datasets are often vector fields: collapse them with `vec_avg` / `vec_sum`
first.

## 6. Prefer simple, interpretable expressions

Fewer operators means fewer degrees of freedom to overfit. The validator warns above 14
operators. Each extra operator should have a reason you can state.

## References

- Ang, A., Hodrick, R. J., Xing, Y., & Zhang, X. (2006). The cross-section of volatility and expected returns. *Journal of Finance*, 61(1), 259-299.
- Asness, C. S., Frazzini, A., Israel, R., Moskowitz, T. J., & Pedersen, L. H. (2018). Size matters, if you control your junk. *Journal of Financial Economics*, 129(3), 479-509.
- Asness, C. S., Frazzini, A., & Pedersen, L. H. (2019). Quality minus junk. *Review of Accounting Studies*, 24(1), 34-112.
- Bernard, V. L., & Thomas, J. K. (1989). Post-earnings-announcement drift: Delayed price response or risk premium? *Journal of Accounting Research*, 27, 1-36.
- Bradshaw, M. T., Richardson, S. A., & Sloan, R. G. (2006). The relation between corporate financing activities, analysts' forecasts and stock returns. *Journal of Accounting and Economics*, 42(1-2), 53-85.
- Campbell, J. Y., Hilscher, J., & Szilagyi, J. (2008). In search of distress risk. *Journal of Finance*, 63(6), 2899-2939.
- Campbell, J. Y., & Vuolteenaho, T. (2004). Bad beta, good beta. *American Economic Review*, 94(5), 1249-1275.
- Cohen, L., & Frazzini, A. (2008). Economic links and predictable returns. *Journal of Finance*, 63(4), 1977-2011.
- Cooper, M. J., Gulen, H., & Schill, M. J. (2008). Asset growth and the cross-section of stock returns. *Journal of Finance*, 63(4), 1609-1651.
- Da, Z., Liu, Q., & Schaumburg, E. (2014). A closer look at the short-term return reversal. *Management Science*, 60(3), 658-674.
- Daniel, K., & Moskowitz, T. J. (2016). Momentum crashes. *Journal of Financial Economics*, 122(2), 221-247.
- Fama, E. F., & French, K. R. (1992). The cross-section of expected stock returns. *Journal of Finance*, 47(2), 427-465.
- Fama, E. F., & French, K. R. (1993). Common risk factors in the returns on stocks and bonds. *Journal of Financial Economics*, 33(1), 3-56.
- Fama, E. F., & French, K. R. (2015). A five-factor asset pricing model. *Journal of Financial Economics*, 116(1), 1-22.
- Frazzini, A., & Pedersen, L. H. (2014). Betting against beta. *Journal of Financial Economics*, 111(1), 1-25.
- Gervais, S., Kaniel, R., & Mingelgrin, D. H. (2001). The high-volume return premium. *Journal of Finance*, 56(3), 877-919.
- Harvey, C. R., Liu, Y., & Zhu, H. (2016). ... and the cross-section of expected returns. *Review of Financial Studies*, 29(1), 5-68.
- Heston, S. L., & Sadka, R. (2008). Seasonality in the cross-section of stock returns. *Journal of Financial Economics*, 87(2), 418-445.
- Hou, K., Xue, C., & Zhang, L. (2015). Digesting anomalies: An investment approach. *Review of Financial Studies*, 28(3), 650-705.
- Hou, K., Xue, C., & Zhang, L. (2020). Replicating anomalies. *Review of Financial Studies*, 33(5), 2019-2133.
- Jegadeesh, N. (1990). Evidence of predictable behavior of security returns. *Journal of Finance*, 45(3), 881-898.
- Jegadeesh, N., & Titman, S. (1993). Returns to buying winners and selling losers. *Journal of Finance*, 48(1), 65-91.
- Jensen, T. I., Kelly, B., & Pedersen, L. H. (2023). Is there a replication crisis in finance? *Journal of Finance*, 78(5), 2465-2518.
- Kakushadze, Z. (2016). 101 formulaic alphas. *Wilmott*, 2016(84), 72-81.
- Lehmann, B. N. (1990). Fads, martingales, and market efficiency. *Quarterly Journal of Economics*, 105(1), 1-28.
- Novy-Marx, R. (2013). The other side of value: The gross profitability premium. *Journal of Financial Economics*, 108(1), 1-28.
- Novy-Marx, R., & Velikov, M. (2022). Betting against betting against beta. *Journal of Financial Economics*, 143(1), 80-106.
- Sloan, R. G. (1996). Do stock prices fully reflect information in accruals and cash flows about future earnings? *The Accounting Review*, 71(3), 289-315.
