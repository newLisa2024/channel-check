"""All database operations in one place, so handlers and the worker stay short."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .db import ChannelSnapshot, Check, Event, Payment, User, utcnow


# --- users -------------------------------------------------------------------

async def get_or_create_user(s: AsyncSession, user_id: int, language: str, free_checks: int,
                             referred_by: int | None = None) -> tuple[User, bool]:
    user = await s.get(User, user_id)
    if user:
        user.last_seen_at = utcnow()
        await s.commit()
        return user, False
    user = User(id=user_id, language=language, free_checks_left=free_checks,
                referred_by=referred_by if referred_by != user_id else None)
    s.add(user)
    try:
        await s.commit()
    except IntegrityError:  # created concurrently by another update
        await s.rollback()
        user = await s.get(User, user_id)
        return user, False
    return user, True


async def set_language(s: AsyncSession, user_id: int, language: str) -> None:
    await s.execute(update(User).where(User.id == user_id).values(language=language))
    await s.commit()


# --- credits -----------------------------------------------------------------

async def reserve_credit(s: AsyncSession, user_id: int) -> str | None:
    """Atomically takes one check from the balance: free first, then paid.
    Returns "free" / "paid", or None if the balance is empty."""
    for kind, column in (("free", User.free_checks_left), ("paid", User.paid_checks_left)):
        result = await s.execute(
            update(User).where(User.id == user_id, column > 0).values({column: column - 1}).returning(User.id)
        )
        if result.first():
            await s.commit()
            return kind
    await s.rollback()
    return None


async def return_credit(s: AsyncSession, user_id: int, kind: str) -> None:
    if kind == "free":
        await s.execute(update(User).where(User.id == user_id).values(free_checks_left=User.free_checks_left + 1))
    elif kind == "paid":
        await s.execute(update(User).where(User.id == user_id).values(paid_checks_left=User.paid_checks_left + 1))
    await s.commit()


async def add_paid_checks(s: AsyncSession, user_id: int, checks: int) -> None:
    await s.execute(update(User).where(User.id == user_id).values(paid_checks_left=User.paid_checks_left + checks))
    await s.commit()


# --- checks and cache --------------------------------------------------------

async def own_recent_check(s: AsyncSession, user_id: int, channel: str, hours: int) -> Check | None:
    """The same user checked the same channel recently: show it again for free."""
    since = utcnow() - timedelta(hours=hours)
    result = await s.execute(
        select(Check).where(Check.user_id == user_id, Check.channel_username == channel,
                            Check.status == "ok", Check.created_at >= since)
        .order_by(Check.created_at.desc()).limit(1)
    )
    return result.scalars().first()


async def cached_check(s: AsyncSession, channel: str, hours: int) -> Check | None:
    """Anyone checked this channel recently: reuse the result instead of loading t.me again."""
    since = utcnow() - timedelta(hours=hours)
    result = await s.execute(
        select(Check).where(Check.channel_username == channel, Check.status == "ok",
                            Check.from_cache.is_(False), Check.created_at >= since)
        .order_by(Check.created_at.desc()).limit(1)
    )
    return result.scalars().first()


async def create_check(s: AsyncSession, **fields) -> Check:
    check = Check(**fields)
    s.add(check)
    await s.commit()
    await s.refresh(check)
    return check


async def finish_check_ok(s: AsyncSession, check: Check, report: dict) -> None:
    check.status = "ok"
    check.report = report
    check.verdict = report.get("verdict")
    check.finished_at = utcnow()
    ch = report.get("channel") or {}
    s.add(ChannelSnapshot(
        channel_username=check.channel_username, subscribers=ch.get("subscribers"),
        median_views=report.get("median_views"), err=report.get("err"), posts_per_day=report.get("posts_per_day"),
    ))
    await s.commit()


async def finish_check_error(s: AsyncSession, check: Check, code: str, text: str) -> None:
    check.status = "error"
    check.error_code = code
    check.error_text = text[:1000]
    check.finished_at = utcnow()
    await s.commit()


# --- payments ----------------------------------------------------------------

async def record_payment(s: AsyncSession, user_id: int, product: str, checks: int, stars: int,
                         charge_id: str) -> bool:
    """Saves the payment and credits the checks. Returns False if this charge was already processed."""
    s.add(Payment(user_id=user_id, product=product, checks=checks, stars=stars, charge_id=charge_id))
    try:
        await s.flush()
    except IntegrityError:
        await s.rollback()
        return False
    await s.execute(update(User).where(User.id == user_id).values(paid_checks_left=User.paid_checks_left + checks))
    await s.commit()
    return True


async def mark_refunded(s: AsyncSession, charge_id: str) -> Payment | None:
    result = await s.execute(select(Payment).where(Payment.charge_id == charge_id))
    payment = result.scalars().first()
    if not payment or payment.status == "refunded":
        return None
    payment.status = "refunded"
    # take back the checks that are still unused
    user = await s.get(User, payment.user_id)
    if user:
        user.paid_checks_left = max(user.paid_checks_left - payment.checks, 0)
    await s.commit()
    return payment


# --- events ------------------------------------------------------------------

async def log_event(s: AsyncSession, user_id: int | None, type_: str, **meta) -> None:
    s.add(Event(user_id=user_id, type=type_, meta=meta or None))
    await s.commit()
