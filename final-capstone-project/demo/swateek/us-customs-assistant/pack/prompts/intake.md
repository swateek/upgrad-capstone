Extract the traveller's facts from their messages. Do not answer their question and do not compute anything. Use null for anything they did not state; never guess a fact.

Fields:
- profile: age (number), trip_hours (number of hours, or "<48" / ">=48" if only that is clear), arrived_directly_from (ISO 2-letter country the flight or crossing came from), exemption_used_last_30_days (true/false), arrival_state (US state code), us_resident (false only if they say they are not a US resident).
- basket: one entry per item line: item (wine, sparkling_wine, beer, spirits, liqueur, hard_cider, cigarettes, cigars, other), quantity, unit (bottle, can, carton, pack, each, fifth, magnum, ml, l), container_ml, abv (% alcohol), value_usd (total paid for the whole line), origin (ISO country where it was MADE, "unknown" if they say they don't know), bought_in (ISO country, or "duty_free"), brand, us_made_export_labelled (cigarettes only).

Reply with ONLY the JSON object {"profile": {...}, "basket": [...]}.
