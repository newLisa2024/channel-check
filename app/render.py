"""Builds Telegram messages from a stored report (the dict from tgcheck.report.to_dict).

Works from the stored dict, not from the engine objects, so a cached report can be shown
again later with a different ad price or in another language."""

from __future__ import annotations

from tgcheck.report import FLAG_TEXT, TEXT

from .i18n import t

ORDER = {"red": 0, "yellow": 1, "green": 2}
ICON = {"red": "🔴", "yellow": "🟡", "green": "🟢"}


def _lang(lang: str) -> str:
    return lang if lang in TEXT else "en"


def _num(n, na: str) -> str:
    return f"{n:,}".replace(",", " ") if isinstance(n, (int, float)) and n is not None else na


def cpm(report: dict, price: float | None) -> float | None:
    median = report.get("median_views")
    if not price or not median:
        return None
    return round(price / (median / 1000), 2)


def _header(report: dict, lang: str, price: float | None) -> list[str]:
    tx = TEXT[lang]
    ch = report.get("channel") or {}
    title = ch.get("title") or "@" + ch.get("username", "")
    lines = [f"📊 {title} (@{ch.get('username', '')}){' ✔️' if ch.get('verified') else ''}", "",
             tx["verdict"][report.get("verdict", "unknown")],
             f"{tx['conf']}: {tx['confidence'][report.get('confidence', 'low')]}"]
    if report.get("median_views"):
        lines.append(tx["reach"].format(n=_num(report["median_views"], tx["na"])))
        value = cpm(report, price)
        if value is not None:
            lines.append(tx["reach_price"].format(cpm=value))
    return lines


def _flag_lines(report: dict, lang: str, limit: int | None = None) -> list[str]:
    fx = FLAG_TEXT[lang]
    flags = sorted(report.get("flags") or [], key=lambda f: ORDER.get(f["level"], 3))
    if limit:
        flags = flags[:limit]
    return [f"{ICON.get(f['level'], '•')} {fx[f['code']].format(**f['params'])}" for f in flags if f["code"] in fx]


def summary(report: dict, lang: str, price: float | None = None) -> str:
    lang = _lang(lang)
    lines = _header(report, lang, price)
    findings = _flag_lines(report, lang, limit=3)
    if findings:
        lines += ["", t(lang, "summary_findings")] + findings
    lines += ["", f"ℹ️ {TEXT[lang]['note']}"]
    return "\n".join(lines)


def full(report: dict, lang: str, price: float | None = None) -> str:
    lang = _lang(lang)
    tx = TEXT[lang]
    na = tx["na"]
    ch = report.get("channel") or {}
    lines = _header(report, lang, price) + ["",
             f"• {tx['subs']}: {_num(ch.get('subscribers'), na)}",
             f"• {tx['posts']}: {report.get('posts_analyzed', 0)}"]
    if report.get("first_post") and report.get("last_post"):
        lines.append(f"• {tx['period']}: {report['first_post'][:10]} → {report['last_post'][:10]}")
    if report.get("posts_per_day") is not None:
        lines.append(f"• {tx['freq']}: {report['posts_per_day']}")
    lines.append(f"• {tx['median']}: {_num(report.get('median_views'), na)}")
    err = report.get("err")
    lines.append(f"• {tx['err']}: {err * 100:.1f}%" if err is not None else f"• {tx['err']}: {na}")
    rr = report.get("reaction_rate")
    lines.append(f"• {tx['reactions']}: {rr * 100:.2f}%" if rr is not None else f"• {tx['reactions']}: {tx['reactions_off']}")
    if report.get("ad_share") is not None:
        lines.append(f"• {tx['ads']}: {report['ad_share'] * 100:.0f}%")
    promoted = report.get("promoted_channels") or []
    if promoted:
        names = ", ".join(f"@{n}" if not str(n).startswith("+") else "private link" for n, _ in promoted[:5])
        lines.append(f"• {tx['promoted']}: {names}")
    flags = _flag_lines(report, lang)
    if flags:
        lines += ["", f"{tx['flags']}:"] + flags
    top = report.get("top_posts") or []
    if top:
        lines += ["", f"{tx['top']}:"] + [f"• t.me/{ch.get('username')}/{p['id']}: {_num(p.get('views'), na)} {tx['views']}" for p in top]
    lines += ["", f"ℹ️ {tx['note']}"]
    return "\n".join(lines)
