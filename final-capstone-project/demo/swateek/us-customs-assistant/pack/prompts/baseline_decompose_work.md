Step 2 of 3. Using the extracted facts, work out the customs result. Do not write the reply yet.

Reply with ONLY a JSON object with:
- "missing_fact": the one fact you still need to answer (or null)
- "exemption_usd": the duty-free exemption that applies (or null)
- "prohibited": items that cannot come in, with the reason
- "over_allowance": for each item over the duty-free allowance: description, amount over, its value, the duty, the excise tax
- "total_owed_usd": the total owed (number)
- "rules": the regulations used
