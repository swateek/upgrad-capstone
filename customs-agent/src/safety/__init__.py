"""Guard (questions) and sanitiser (retrieved documents): code, before any model sees the text."""

from src.safety.guard import GuardResult, check_question, sanitise_clause

__all__ = ["GuardResult", "check_question", "sanitise_clause"]
