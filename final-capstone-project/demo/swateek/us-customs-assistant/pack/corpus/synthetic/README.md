# Synthetic injection fixtures

Made-up documents for the prompt-injection tests (plan §7, eval category `injection_doc`). Each one reads like ordinary traveller material and contains a planted instruction aimed at the model. The system must treat retrieved text as data: it never follows these instructions, and their claims never change an answer (figures come from the calculators and the signed-off rule table).

They are indexed with the real corpus so retrieval can surface them. Every chunk is marked `synthetic: true` and `role: injection_fixture`, and its citation starts with "Synthetic fixture". None of this text comes from, or speaks for, any agency.
