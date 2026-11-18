Extract the traveller's facts from their message. Do not answer their question and do not compute anything. Use null for anything they did not state; never guess a fact.

Fields:
- profile: age (number), trip_hours (number of hours, or "<48" / ">=48" if only that is clear; a week is 168), arrived_directly_from (ISO 2-letter country the flight or crossing came from), countries_visited (ISO codes), exemption_used_last_30_days (true/false; "first trip this year" means false), arrival_state (US state code), us_resident (false only if they say they are not a US resident), travelling_as_family, crew (true only if they are crew on duty), shipped (true only if the goods are shipped or mailed).
- basket: one entry per item line: item (wine, sparkling_wine, beer, spirits, liqueur, hard_cider, cigarettes, cigars, other), quantity, unit (bottle, can, carton, pack, box, each, fifth, magnum, ml, l), container_ml, abv (% alcohol), value_usd (total paid for the whole line, not per unit), origin (ISO country where it was MADE, "unknown" if they say they don't know), bought_in (ISO country, or "duty_free"), brand, us_made_export_labelled (cigarettes only), other_kind (for item "other": "vapes_nicotine" for vapes, e-cigarettes or nicotine products, else "other_goods").

If CURRENT FACTS are given, the message is a reply or a correction: start from the current facts, change only what the message changes, add anything new, and keep everything else exactly as it was. Return the complete updated facts.

Reply with ONLY the JSON object {"profile": {...}, "basket": [...]}.
