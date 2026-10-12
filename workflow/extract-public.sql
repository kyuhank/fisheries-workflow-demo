-- Published aggregates, not individual fishing sets. Keep the fixed observed support.
SELECT set_id, source_row, year, fleet, quarter, cell, stratum, hooks, catch_n
FROM sets
WHERE fleet = 'FJ' AND hooks > 0 AND catch_n >= 0
  AND stratum IN ('20S_170E_Q4', '20S_175E_Q1', '20S_175E_Q2',
                  '20S_175E_Q3', '20S_175E_Q4', '25S_175E_Q3')
ORDER BY year, cell, quarter, source_row;
