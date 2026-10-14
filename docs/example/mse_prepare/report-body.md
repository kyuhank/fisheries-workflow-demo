# Prepare MSE

4 fitted stock cases · 3 catch rules · 15 future years · 20 trials per case and scenario.

## Starting stocks

  Assessment case   First future year   Starting B / K   Reference catch (t/year)
  ----------------- ------------------- ---------------- --------------------------
  Assessment A1     2022                0.4952           7.359e+04
  Assessment A2     2022                0.4909           7.359e+04
  Assessment B1     2022                0.4774           7.359e+04
  Assessment B2     2022                0.474            7.359e+04

Trials start after the last observed catch, using the fitted next-year biomass. Future growth and observation errors are declared assumptions.

Every rule faces the same recorded scenarios and random errors. The Buffered rule job supplies the catch buffer actually tested.

The selected Fiji fleet index is not a validated stock-wide abundance index. Using it with stock-wide catches is a teaching assumption.

The shared guardrail caps realised catch at 40% of true starting biomass. Biomass and low-biomass statistics are conditional on that safeguard.
