Extract the traveller's facts from their message. Do not answer their question and do not compute anything. Use null for anything they did not state; never guess or infer a fact.

Fields:
- profile:
  - age (number).
  - trip_hours: how long they were away, as a number of hours (a day = 24, 6 days = 144, a week = 168, 10 days = 240). Null if they don't give a length.
  - trip_at_least_48_hours: only when trip_hours is null but they say something like "a day trip" (false) or "a long trip" (true); otherwise null.
  - arrived_directly_from: ISO 2-letter code of the country the flight or crossing came from. A city or region means its country (Toronto = CA, Ensenada = MX, Bavaria = DE).
  - countries_visited: ISO codes.
  - exemption_used_last_30_days: true/false; "first trip this year" or "haven't used it this month" means false.
  - arrival_state: US state code, only if they name the US state or city they land in.
  - us_resident: keep true. Set false only if they say they don't live in the US.
  - crew: true only if they say they are crew on duty. shipped: true only if they say the goods are shipped or mailed.
  - scope_quote: if you set us_resident false, crew true or shipped true, copy the traveller's exact words that say so; otherwise null.
  - travelling_as_family: true only if they say they travel with family members.
- basket: one entry per item line:
  - item: wine, sparkling_wine, beer, spirits, liqueur, hard_cider, cigarettes, cigars, or other. Cigars and cigarettes are different items. Use "other" only for goods that are not alcohol or tobacco (perfume, a watch, food), and list those too.
  - quantity, unit (bottle, can, carton, pack, box, each, fifth, magnum, ml, l), container_ml, abv (% alcohol).
  - value_usd: the total paid for the whole line (2 bottles at $25 each = 50). Null if no price is given.
  - origin: ISO code of the country where it was MADE, only if they say so ("French wine", "made in", what the label says); "unknown" if they say they don't know. Never take the origin from a brand name or from where it was bought.
  - bought_in: ISO code, or "duty_free"; brand; us_made_export_labelled (cigarettes only).
  - other_kind (item "other" only): "vapes_nicotine" for vapes, e-cigarettes or nicotine products, else "other_goods".

If CURRENT FACTS are given, the message is a reply or a correction: start from the current facts, change only what the message changes, and keep everything else exactly as it was. A reply to your question fills in the missing fact on the existing line (for example its origin); add a line only for a new item. Return the complete updated facts.

Reply with ONLY the JSON object {"profile": {...}, "basket": [...]}.
