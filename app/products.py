"""What can be bought. Prices are in Telegram Stars (currency XTR)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Pack:
    key: str
    checks: int
    stars: int


PACKS: dict[str, Pack] = {
    "p1": Pack("p1", 1, 50),
    "p5": Pack("p5", 5, 200),
    "p20": Pack("p20", 20, 600),
}


def invoice_payload(pack: Pack, user_id: int) -> str:
    return f"pack:{pack.key}:{user_id}"


def parse_payload(payload: str) -> tuple[Pack, int] | None:
    try:
        kind, key, user_id = payload.split(":")
        if kind != "pack" or key not in PACKS:
            return None
        return PACKS[key], int(user_id)
    except ValueError:
        return None
