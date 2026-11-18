"""Turns parsed posts into metrics and a buy / caution / avoid verdict.

All thresholds are heuristics collected in THRESHOLDS so they are easy to tune
once we have checked a few dozen real channels.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .parse import ChannelInfo, Post

THRESHOLDS = {
    "mature_post_age_hours": 48,     # views still grow fast during the first 1-2 days
    "min_mature_posts": 8,           # fewer posts -> low confidence
    # Reach (median views / subscribers). Base values for channels posting < 1.5 times a day;
    # frequent posting lowers per-post reach, see FREQUENCY_FACTORS.
    "err_critical": 0.03,            # below this the audience is mostly dead or fake -> red
    "err_low": 0.08,                 # below this: red only together with fake signs, otherwise yellow
    "err_green": 0.20,               # this and above is healthy
    "cv_too_uniform": 0.10,          # views almost identical on every post -> possible bot views
    "reaction_rate_low": 0.002,      # < 0.2% reactions per view on a big channel -> suspicious
    "reaction_rate_high": 0.08,      # > 8% reactions per view is unusual -> check manually
    "reaction_check_min_views": 3000,
    "ad_share_high": 0.40,           # 40%+ of posts are ads -> audience is tired of ads
    "inactive_days": 30,
}

# (min posts per day, multiplier for err_* thresholds)
FREQUENCY_FACTORS = [(3.0, 0.6), (1.5, 0.75), (0.0, 1.0)]


def frequency_factor(posts_per_day: float | None) -> float:
    if posts_per_day is None:
        return 1.0
    for min_ppd, factor in FREQUENCY_FACTORS:
        if posts_per_day >= min_ppd:
            return factor
    return 1.0


@dataclass
class Flag:
    level: str      # "red" | "yellow" | "green"
    code: str       # stable id; the text lives in report.py, per language
    params: dict = field(default_factory=dict)


@dataclass
class Report:
    channel: ChannelInfo
    posts_analyzed: int = 0
    mature_posts: int = 0
    first_post: datetime | None = None
    last_post: datetime | None = None
    posts_per_day: float | None = None
    median_views: int | None = None
    mean_views: int | None = None
    err: float | None = None
    views_cv: float | None = None
    reaction_rate: float | None = None
    reactions_enabled: bool = False
    ad_share: float | None = None
    ad_median_views: int | None = None
    promoted_channels: list[tuple[str, int]] = field(default_factory=list)
    forwarded_share: float | None = None
    price: float | None = None
    cpm: float | None = None
    err_factor: float = 1.0
    flags: list[Flag] = field(default_factory=list)
    verdict: str = "unknown"    # green | yellow | red | unknown
    confidence: str = "low"     # low | medium | high
    top_posts: list[Post] = field(default_factory=list)


def _median(values: list[int]) -> int | None:
    return int(statistics.median(values)) if values else None


def analyze(channel: ChannelInfo, posts: list[Post], price: float | None = None,
            now: datetime | None = None) -> Report:
    now = now or datetime.now(timezone.utc)
    t = THRESHOLDS
    report = Report(channel=channel, posts_analyzed=len(posts), price=price)

    if not channel.preview_available:
        report.flags.append(Flag("yellow", "no_preview", {}))
        return report
    if not posts:
        report.flags.append(Flag("yellow", "no_posts", {}))
        return report

    dated = [p for p in posts if p.date]
    if dated:
        report.first_post = min(p.date for p in dated)
        report.last_post = max(p.date for p in dated)
        span_days = max((report.last_post - report.first_post).total_seconds() / 86400, 1)
        report.posts_per_day = round(len(dated) / span_days, 2)

    # Only "mature" posts: fresh ones haven't collected their views yet.
    cutoff = now - timedelta(hours=t["mature_post_age_hours"])
    mature = [p for p in posts if p.views is not None and p.date and p.date <= cutoff and not p.forwarded]
    report.mature_posts = len(mature)
    views = [p.views for p in mature]
    report.median_views = _median(views)
    report.mean_views = int(statistics.mean(views)) if views else None

    if report.median_views and channel.subscribers:
        report.err = report.median_views / channel.subscribers
    if len(views) >= 5 and report.mean_views:
        report.views_cv = statistics.pstdev(views) / report.mean_views

    report.reactions_enabled = any(p.has_reactions_block for p in posts)
    if report.reactions_enabled and views:
        report.reaction_rate = sum(p.reactions for p in mature) / max(sum(views), 1)

    own_posts = [p for p in posts if not p.forwarded]
    if own_posts:
        ads = [p for p in own_posts if p.likely_ad]
        report.ad_share = len(ads) / len(own_posts)
        report.ad_median_views = _median([p.views for p in ads if p.views is not None and p in mature])
        counts: dict[str, int] = {}
        for p in ads:
            for name in p.promo_of:
                counts[name] = counts.get(name, 0) + 1
        report.promoted_channels = sorted(counts.items(), key=lambda kv: -kv[1])[:10]
    report.forwarded_share = sum(p.forwarded for p in posts) / len(posts)

    if price and report.median_views:
        # What the advertiser pays per 1,000 expected views (median, not best-case).
        report.cpm = round(price / (report.median_views / 1000), 2)

    report.top_posts = sorted(mature, key=lambda p: p.views or 0, reverse=True)[:3]

    _score(report, now)
    return report


def _score(r: Report, now: datetime) -> None:
    t = THRESHOLDS
    flags = r.flags
    r.err_factor = frequency_factor(r.posts_per_day)
    err_critical = t["err_critical"] * r.err_factor
    err_low = t["err_low"] * r.err_factor
    err_green = t["err_green"] * r.err_factor

    if r.mature_posts >= 30:
        r.confidence = "high"
    elif r.mature_posts >= t["min_mature_posts"]:
        r.confidence = "medium"
    else:
        flags.append(Flag("yellow", "few_posts", {"n": r.mature_posts}))

    # Signs of bought views / fake audience, evaluated before the reach verdict.
    uniform = r.views_cv is not None and r.mature_posts >= 15 and r.views_cv < t["cv_too_uniform"]
    big_enough = (r.median_views or 0) >= t["reaction_check_min_views"]
    low_reactions = r.reaction_rate is not None and big_enough and r.reaction_rate < t["reaction_rate_low"]
    fake_signs = uniform or low_reactions

    if r.err is not None:
        pct = r.err * 100
        if r.err < err_critical:
            flags.append(Flag("red", "very_low_err", {"pct": pct}))
        elif r.err < err_low:
            if fake_signs:
                flags.append(Flag("red", "low_err", {"pct": pct}))
            else:
                flags.append(Flag("yellow", "inactive_subs", {"pct": pct}))
        elif r.err < err_green:
            flags.append(Flag("yellow", "mid_err", {"pct": pct}))
        else:
            flags.append(Flag("green", "good_err", {"pct": pct}))
        if r.err > 1.5:
            flags.append(Flag("yellow", "views_exceed_subs", {}))
        if r.err_factor < 1.0:
            flags.append(Flag("green", "frequent_posting", {"ppd": r.posts_per_day}))
    elif r.channel.subscribers is None:
        flags.append(Flag("yellow", "no_subs", {}))

    if uniform:
        flags.append(Flag("red", "uniform_views", {}))

    if r.reaction_rate is not None and big_enough:
        if low_reactions:
            flags.append(Flag("yellow", "low_reactions", {"pct": r.reaction_rate * 100}))
        elif r.reaction_rate > t["reaction_rate_high"]:
            flags.append(Flag("yellow", "high_reactions", {"pct": r.reaction_rate * 100}))
        else:
            flags.append(Flag("green", "reactions_ok", {"pct": r.reaction_rate * 100}))

    if r.ad_share is not None:
        if r.ad_share >= t["ad_share_high"]:
            flags.append(Flag("yellow", "ad_heavy", {"pct": r.ad_share * 100}))
        if r.ad_median_views and r.median_views and r.ad_median_views < 0.6 * r.median_views:
            flags.append(Flag("yellow", "ads_underperform", {}))

    if r.last_post and now - r.last_post > timedelta(days=t["inactive_days"]):
        flags.append(Flag("red", "inactive", {"days": (now - r.last_post).days}))

    reds = sum(f.level == "red" for f in flags)
    yellows = sum(f.level == "yellow" for f in flags)
    if r.err is None and r.median_views is None:
        r.verdict = "unknown"
    elif reds:
        r.verdict = "red"
    elif yellows >= 2 or r.confidence == "low":
        r.verdict = "yellow"
    else:
        r.verdict = "green" if r.err is not None and r.err >= err_green else "yellow"
