# Draft correction: business case, example 4 (Tijuana day trip)

**Status: draft for review.** Not yet sent to the mentor or edited into the business case PDF.

## What the business case says (example 4)

> Traveller: "Day trip to Tijuana. I bought one 750 ml bottle of tequila."
> Assistant answers: Because you were away under 48 hours, your exemption is $200 and holds only 150 ml of alcohol. The other 600 ml is over the allowance, so declare the bottle. Federal excise on 600 ml of 40% spirits is about $1.71, plus any duty, and California may add its own tax.
> Sources: 19 CFR 148.51; TTB tax rates.

## Why it is wrong

- A returning resident who arrives **directly from Mexico** gets the $800 exemption whatever the time away. The 48-hour rule does not apply (19 CFR 148.35(a); signed off as rule R9 in `docs/regulatory-checks.md`).
- A single 750 ml bottle is within the 1-litre alcohol allowance, so there is no excess and no excise on it.
- The $200 exemption with its 150 ml cap applies only to short trips that do not come directly from Mexico (19 CFR 148.51).

## Proposed replacement

> Traveller: "Day trip to Tijuana. I'm 30, haven't used my exemption in the last 30 days, and I bought one 750 ml bottle of tequila for $35. Do I owe anything?"
> Assistant answers: Nothing is owed on the tequila. You arrived directly from Mexico, so the $800 exemption applies whatever the time away (19 CFR 148.35(a)). One 750 ml bottle is within the 1-litre alcohol allowance. Your arrival state may set its own limits or taxes on alcohol.
> Sources: 19 CFR 148.35(a); CBP, What to Expect When You Return.

## Open points for the team

1. **Question wording.** The business case question has no age or exemption answers. The eval scenario uses age 30 and no exemption in the last 30 days, which the assistant asks for first. Keep the question as in the eval set, or add those facts.
2. **Citation in the app.** The signed-off rule cites 19 CFR 148.35(a). The live answer's working cites the CBP "What to Expect When You Return" page instead. The demo script expects 148.35(a). Decide which the card should show, then align the rule table or the script.
3. **Price.** The business case gives no price. The demo script and frozen eval use $35; the web page's example chip now also uses $35.
