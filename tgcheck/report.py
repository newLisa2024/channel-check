"""Renders a Report as text (English / Russian) or as a JSON-ready dict."""

from __future__ import annotations

from .metrics import Report

FLAG_TEXT = {
    "en": {
        "no_preview": "The channel has disabled its public web preview, so post views can't be checked.",
        "no_posts": "No public posts found.",
        "few_posts": "Only {n} posts are old enough to judge reach, so the verdict is a rough estimate.",
        "very_low_err": "Only {pct:.1f}% of subscribers see a typical post. Most subscribers never see the posts (inactive or fake): pay only for real views, not for the subscriber count.",
        "low_err": "Only {pct:.1f}% of subscribers see a typical post, and there are signs of bought views or followers.",
        "inactive_subs": "Only {pct:.1f}% of subscribers see a typical post. The readers look real, but many subscribers are inactive: pay for actual views, not for the subscriber count.",
        "frequent_posting": "The channel posts often ({ppd:.1f} posts a day), so each post naturally gets a smaller share of subscribers. Reach thresholds were adjusted.",
        "high_reactions": "Unusually many reactions ({pct:.2f}% of views). It may be a very loyal audience, but reactions can also be bought: check a few posts manually.",
        "mid_err": "A typical post reaches {pct:.1f}% of subscribers (average).",
        "good_err": "A typical post reaches {pct:.1f}% of subscribers (healthy).",
        "views_exceed_subs": "Posts get more views than the channel has subscribers: reach may come from reposts, or views may be boosted.",
        "no_subs": "Subscriber count is hidden, so reach can't be compared to audience size.",
        "uniform_views": "Views are almost identical on every post. Real audiences vary; this pattern often means bought views.",
        "uniform_views_check": "Views are almost identical on every post. It happens with a small loyal audience, but also with bought views: look at a few posts manually.",
        "high_err": "Unusually high reach: {pct:.1f}% of subscribers see a typical post. It may be a very engaged audience, but views can also be boosted.",
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
        "very_low_err": "Обычный пост видят только {pct:.1f}% подписчиков. Большинство подписчиков посты не видит (неактивны или ненастоящие): платите только за реальные просмотры, а не за число подписчиков.",
        "low_err": "Обычный пост видят только {pct:.1f}% подписчиков, и есть признаки накрутки просмотров или подписчиков.",
        "inactive_subs": "Обычный пост видят только {pct:.1f}% подписчиков. Читатели выглядят живыми, но многие подписчики неактивны: платите за реальные просмотры, а не за число подписчиков.",
        "frequent_posting": "Канал публикует часто ({ppd:.1f} поста в день), поэтому каждый пост естественно видит меньшая доля подписчиков. Пороги охвата скорректированы.",
        "high_reactions": "Необычно много реакций ({pct:.2f}% от просмотров). Это может быть очень лояльная аудитория, но реакции тоже накручивают: проверьте пару постов вручную.",
        "mid_err": "Обычный пост видят {pct:.1f}% подписчиков (средний уровень).",
        "good_err": "Обычный пост видят {pct:.1f}% подписчиков (хороший уровень).",
        "views_exceed_subs": "Просмотров больше, чем подписчиков: охват может идти из репостов, а может быть накручен.",
        "no_subs": "Число подписчиков скрыто, поэтому охват не с чем сравнить.",
        "uniform_views": "Просмотры почти одинаковые на каждом посте. У живой аудитории они колеблются, а такая картина часто означает накрутку.",
        "uniform_views_check": "Просмотры почти одинаковые на каждом посте. Так бывает у небольшой преданной аудитории, но и при накрутке: посмотрите несколько постов вручную.",
        "high_err": "Необычно высокий охват: обычный пост видят {pct:.1f}% подписчиков. Это может быть очень вовлечённая аудитория, но просмотры тоже накручивают.",
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
        "reach": "👀 Your ad post will most likely be seen by about {n} people",
        "reach_price": "💰 At your price that is {cpm} per 1,000 real views",
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
        "reach": "👀 Ваш рекламный пост, скорее всего, увидят около {n} человек",
        "reach_price": "💰 При вашей цене это {cpm} за 1000 реальных просмотров",
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
    ]
    if r.median_views:
        lines.append(tx["reach"].format(n=_num(r.median_views, na)))
        if r.cpm is not None:
            lines.append(tx["reach_price"].format(cpm=r.cpm))
    lines += [
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
        "price": r.price, "cpm": r.cpm, "err_factor": r.err_factor,
        "flags": [{"level": f.level, "code": f.code, "params": f.params} for f in r.flags],
        "top_posts": [{"id": p.id, "views": p.views} for p in r.top_posts],
    }
