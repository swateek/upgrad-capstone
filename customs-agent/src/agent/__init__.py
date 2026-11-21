"""DeclareRight agent: guard -> intake -> router (code) or planner (LLM) -> tools -> writer -> verifier.

v0 uses the code router (src/agent/router.py): the tools run in a fixed order. The LLM planner
(Days 5-7, next) replaces only that step, so a change in score belongs to the planner.
"""
