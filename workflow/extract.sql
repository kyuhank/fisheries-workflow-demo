-- Toy extraction: keep valid effort, retain zero catches, preserve vessel identity.
SELECT set_id, year, vessel, hooks, catch_n
FROM sets
WHERE hooks > 0 AND catch_n >= 0
ORDER BY year, set_id;

