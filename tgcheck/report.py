"""Renders a Report as text (English / Russian) or as a JSON-ready dict."""

from __future__ import annotations

from .metrics import Report

FLAG_TEXT = {
    "en": {
        "no_preview": "The channel has disabled its public web preview, so post views can't be checked.",
        "no_posts": "No public posts found.",
        "few_posts": "Only {n} posts are old enough to judge reach, so the verdict is a rough estimate.",
        "low_err": "Only {pct:.1f}% of subscribers see a typical post. Many subscribers are inactive or fake.",
        "mid_err": "A typical post reaches {pct:.1f}% of subscribers (average).",
        "good_err": "A typical post reaches {pct:.1f}% of subscribers (healthy).",
        "views_exceed_subs": "Posts get far more views than the channel has subscribers: reach may come from reposts, or views may be boosted.",
        "no_subs": "Subscriber count is hidden, so reach can't be compared to audience size.",
        "uniform_views": "Views are almost identical on every post. Real audiences vary; this pattern often means bought views.",
        "low_reactions": "Very few reactions ({pct:.2f}% of views) for a channel this size.",
        "reactions_ok": "Reactions look natural ({pct:.2f}% of views).",
        "ad_heavy": "{pct:.0f}% of posts look like ads. The audience may ignore yet another one.",
        "ads_underperform": "Ad posts get noticeably fewer views than regular posts.",
        "inactive": "No posts in the last {days} days.",
    },
    "ru": {
        "no_preview": "У канала отключён публичный веб-просмотр, поэтому охваты постов проверить нельзя.",
        "no_posts": "Публичных постов не найдено.",
        "few_posts": "Для оценки охвата достаточно «взрослых» постов только {n}, поэтому вывод приблизительный.",
        "low_err": "Обычный пост видят только {pct:.1f}% подписчиков. Много неактивных или ненастоящих подписчиков.",
        "mid_err": "Обычный пост видят {pct:.1f}% подписчиков (средний уровень).",
        "good_err": "Обычный пост видят {pct:.1f}% подписчиков (хороший уровень).",
        "views_exceed_subs": "Просмотров намного больше, чем подписчиков: охват может идти из репостов, а может быть накручен.",
        "no_subs": "Число подписчиков скрыто, поэтому охват не с чем сравнить.",
        "uniform_views": "Просмотры почти одинаковые на каждом посте. У живой аудитории они колеблются, а такая картина часто означает накрутку.",
        "low_reactions": "Очень мало реакций ({pct:.2f}% от просмотров) для канала такого размера.",
        "reactions_ok": "Реакции выглядят естественно ({pct:.2f}% от просмотров).",
        "ad_heavy": "{pct:.0f}% постов похожи на рекламу. Ещё одну рекламу аудитория может просто пролистать.",
        "ads_underperform": "Рекламные посты набирают заметно меньше просмотров, чем обычные.",
        "inactive": "Постов не было уже {days} дн.",
    },
}

TEXT = {
    "en": {
        "verdict": {"green": "🟢 The audience looks real", "yellow": "🟡 Mixed signals, check carefully",
                    "red": "🔴 Looks like fake or inactive audience", "unknown": "⚪ Not enough data"},
        "confidence": {"low": "low", "medium": "medium", "high": "high"},
        "subs": "Subscribers", "posts": "Posts analyzed", "period": "Period", "freq": "Posts per day",
        "median": "Typical post views (median)", "err": "Reach (views / subscribers)",
        "reactions": "Reactions per view", "reactions_off": "reactions disabled",
        "ads": "Posts that look like ads", "promoted": "Channels promoted here recently",
        "cpm": "Your price per 1,000 views", "conf": "Confidence", "top": "Top posts",
        "flags": "Findings", "na": "n/a", "views": "views",
        "note": "Heuristic estimate from public data only. Always compare with other channels in the same niche.",
    },
    "ru": {
        "verdict": {"green": "🟢 Аудитория выглядит живой", "yellow": "🟡 Есть сомнения, проверьте внимательнее",
                    "red": "🔴 Похоже на накрутку или неактивную аудиторию", "unknown": "⚪ Недостаточно данных"},
        "confidence": {"low": "низкая", "medium": "средняя", "high": "высокая"},
        "subs": "Подписчики", "posts": "Проанализировано постов", "period": "Период", "freq": "Постов в день",
        "median": "Просмотры обычного поста (медиана)", "err": "Охват (просмотры / подписчики)",
        "reactions": "Реакций на просмотр", "reactions_off": "реакции отключены",
        "ads": "Постов, похожих на рекламу", "promoted": "Каналы, которые здесь недавно рекламировались",
        "cpm": "Ваша цена за 1000 просмотров", "conf": "Уверенность", "top": "Лучшие посты",
        "flags": "Что мы заметили", "na": "н/д", "views": "просмотров",
        "note": "Оценка по публичным данным, это не гарантия. Сравнивайте с другими каналами той же тематики.",
    },
}


def _num(n: int | None, na: str) -> str:
    return f"{n:,}".replace(",", " ") if n is not None else na


def render(r: Report, lang: str = "en") -> str:
    lang = lang if lang in TEXT else "en"
    tx, fx = TEXT[lang], FLAG_TEXT[lang]
    na = tx["na"]
    ch = r.channel
    lines = [
        f"📊 {ch.title or '@' + ch.username} (@{ch.username}){' ✔️' if ch.verified else ''}",
        "",
        f"{tx['verdict'][r.verdict]}",
        f"{tx['conf']}: {tx['confidence'][r.confidence]}",
        "",
        f"• {tx['subs']}: {_num(ch.subscribers, na)}",
        f"• {tx['posts']}: {r.posts_analyzed}",
    ]
    if r.first_post and r.last_post:
        lines.append(f"• {tx['period']}: {r.first_post:%Y-%m-%d} → {r.last_post:%Y-%m-%d}")
    if r.posts_per_day is not None:
        lines.append(f"• {tx['freq']}: {r.posts_per_day}")
    lines.append(f"• {tx['median']}: {_num(r.median_views, na)}")
    lines.append(f"• {tx['err']}: {r.err * 100:.1f}%" if r.err is not None else f"• {tx['err']}: {na}")
    if r.reactions_enabled and r.reaction_rate is not None:
        lines.append(f"• {tx['reactions']}: {r.reaction_rate * 100:.2f}%")
    else:
        lines.append(f"• {tx['reactions']}: {tx['reactions_off']}")
    if r.ad_share is not None:
        lines.append(f"• {tx['ads']}: {r.ad_share * 100:.0f}%")
    if r.promoted_channels:
        names = ", ".join(f"@{n}" if not n.startswith("+") else "private link" for n, _ in r.promoted_channels[:5])
        lines.append(f"• {tx['promoted']}: {names}")
    if r.cpm is not None:
        lines.append(f"• {tx['cpm']}: {r.cpm}")
    if r.flags:
        lines += ["", f"{tx['flags']}:"]
        order = {"red": 0, "yellow": 1, "green": 2}
        icon = {"red": "🔴", "yellow": "🟡", "green": "🟢"}
        for f in sorted(r.flags, key=lambda f: order[f.level]):
            lines.append(f"{icon[f.level]} {fx[f.code].format(**f.params)}")
    if r.top_posts:
        lines += ["", f"{tx['top']}:"]
        for p in r.top_posts:
            lines.append(f"• t.me/{ch.username}/{p.id}: {_num(p.views, na)} {tx['views']}")
    lines += ["", f"ℹ️ {tx['note']}"]
    return "\n".join(lines)


def to_dict(r: Report) -> dict:
    ch = r.channel
    return {
        "channel": {"username": ch.username, "title": ch.title, "subscribers": ch.subscribers,
                    "verified": ch.verified, "preview_available": ch.preview_available},
        "verdict": r.verdict, "confidence": r.confidence,
        "posts_analyzed": r.posts_analyzed, "mature_posts": r.mature_posts,
        "first_post": r.first_post.isoformat() if r.first_post else None,
        "last_post": r.last_post.isoformat() if r.last_post else None,
        "posts_per_day": r.posts_per_day, "median_views": r.median_views, "mean_views": r.mean_views,
        "err": r.err, "views_cv": r.views_cv, "reaction_rate": r.reaction_rate,
        "ad_share": r.ad_share, "ad_median_views": r.ad_median_views,
        "promoted_channels": r.promoted_channels, "forwarded_share": r.forwarded_share,
        "price": r.price, "cpm": r.cpm,
        "flags": [{"level": f.level, "code": f.code, "params": f.params} for f in r.flags],
        "top_posts": [{"id": p.id, "views": p.views} for p in r.top_posts],
    }
