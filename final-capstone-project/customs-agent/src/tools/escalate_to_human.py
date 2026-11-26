"""escalate_to_human: a hand-off note with the facts relied on. It informs; it never files anything."""

from __future__ import annotations

from pydantic import BaseModel

from src.schemas import BasketLine, EscalationNote, Profile


class Args(BaseModel):
    reason: str
    profile: Profile
    basket: list[BasketLine]
    known: dict = {}


def escalate_to_human(args: Args) -> EscalationNote:
    items = (
        "; ".join(
            f"{ln.quantity.value:g} {ln.quantity.unit} {ln.item}" for ln in args.basket
        )
        or "no items"
    )
    summary = (
        f"Needs an officer's decision: {args.reason}. Items: {items}. "
        "Declare everything at entry; this is not a customs ruling."
    )
    return EscalationNote(
        reason=args.reason,
        summary=summary,
        facts={
            "profile": args.profile.model_dump(),
            "basket": [b.model_dump() for b in args.basket],
        },
        known=args.known,
    )
