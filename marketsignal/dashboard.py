"""A static, read-only operations dashboard with no external dependencies."""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from pathlib import Path

from .storage import Storage


def _datetime(timestamp: int | None) -> str:
    if timestamp is None:
        return "—"
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%b %d, %Y · %H:%M UTC")


def _currency(value: float) -> str:
    return f"${value:,.0f}"


def _signal_rows(signals: list[dict], is_demo: bool = False, is_daily: bool = False) -> str:
    if not signals:
        message = ('No movements passed the daily threshold in this snapshot. '
                   'The first day establishes the baseline.' if is_daily else
                   'No qualified changes yet. The detector needs a 1-hour or 24-hour observation baseline.')
        return f'<tr><td colspan="5" class="empty">{message}</td></tr>'
    rows = []
    for signal in signals:
        change = signal["change_pp"]
        direction_class = "up" if change >= 0 else "down"
        slug = escape(signal["event_slug"], quote=True)
        question = escape(signal["question"])
        title = question if is_demo else f'<a href="https://polymarket.com/event/{slug}" target="_blank" rel="noopener noreferrer">{question}</a>'
        rows.append(
            f'<tr><td>{title}'
            f'<div class="minor">{_datetime(signal["observed_at"])}</div></td>'
            f'<td class="num">{signal["previous_price"]:.1%} → {signal["current_price"]:.1%}</td>'
            f'<td class="num {direction_class}">{change:+.1f} pp / {signal["window_hours"]}h</td>'
            f'<td class="num">{signal["score"]}/100</td>'
            f'<td class="num">{_currency(signal["volume_24h"])}</td></tr>'
        )
    return "\n".join(rows)


def _market_rows(markets: list[dict]) -> str:
    if not markets:
        return '<tr><td colspan="4" class="empty">No observations yet. Run `collect`.</td></tr>'
    return "\n".join(
        f'<tr><td>{escape(m["question"])}</td><td class="num">{m["yes_price"]:.1%}</td>'
        f'<td class="num">{_currency(m["volume_24h"])}</td>'
        f'<td class="num">{_currency(m["liquidity"])}</td></tr>'
        for m in markets
    )


def _run_rows(runs: list[dict]) -> str:
    return "\n".join(
        f'<tr><td>{_datetime(r["started_at"])}</td><td><span class="status {"ok" if r["status"] == "ok" else "bad"}">{escape(r["status"])}</span></td>'
        f'<td class="num">{r["markets_saved"]}</td><td class="num">{r["signals_created"]}</td></tr>'
        for r in runs
    ) or '<tr><td colspan="4" class="empty">No runs recorded.</td></tr>'


def render_dashboard(store: Storage, output_file: str | Path) -> Path:
    data = store.dashboard_data()
    stats = data["stats"]
    is_demo = data["dataset"] == "demo"
    is_daily = data["dataset"] == "daily"
    last_run = data["runs"][0] if data["runs"] else None
    if is_daily and last_run:
        latest_bucket = store.bucket(last_run["started_at"])
        data["signals"] = [s for s in data["signals"] if s["observed_at"] == latest_bucket]
    generated_at = _datetime(int(datetime.now(timezone.utc).timestamp()))
    status_label = "Synthetic demonstration" if is_demo else ("Daily market briefing" if is_daily else "Read-only market observations")
    signals_caption = "Daily observations · elapsed interval shown" if is_daily else "Threshold-based signals · 1h and 24h"
    footer_label = "Daily data-only proof of concept · No AI-authored claims" if is_daily else "Prototype v0.2 · Not an autonomous publisher yet"
    warning = (
        '<div class="alert"><strong>DEMO DATA:</strong> All prices and movements on this page are synthetic.</div>'
        if is_demo else
        '<div class="alert">Market outcome prices are trading quotes, not verified real-world probabilities. '
        'No cause of a movement is asserted here. This is a monitoring prototype, not financial advice.</div>'
    )
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>MarketSignal | Operations</title><style>
:root{{--ink:#17242b;--muted:#6b7880;--line:#dce3e5;--teal:#0b615d;--light:#f7f9f9;--up:#16705e;--down:#b8504a}}
*{{box-sizing:border-box}}body{{margin:0;background:#fff;color:var(--ink);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
.layout{{max-width:1160px;margin:0 auto;padding:0 26px 64px}}header{{display:flex;justify-content:space-between;align-items:center;gap:16px;padding:28px 0;border-bottom:1px solid var(--line)}}
.brand{{font:700 22px/1 Georgia,serif;letter-spacing:-.5px}}.brand span{{color:var(--teal)}}.pill{{font-size:12px;color:var(--teal);background:#eaf5f0;border-radius:22px;padding:7px 12px}}
h1{{font:normal 48px/1.1 Georgia,serif;letter-spacing:-1px;margin:44px 0 10px}}.lead{{font-size:16px;color:var(--muted);margin:0 0 30px}}
.metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:26px 0 40px}}.metric{{background:var(--light);border:1px solid var(--line);padding:24px;border-radius:10px}}
.metric strong{{display:block;font-size:30px;font-variant-numeric:tabular-nums;letter-spacing:-1px}}.metric span{{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.6px}}
section{{margin-top:39px}}.sectionhead{{display:flex;justify-content:space-between;align-items:flex-end;gap:12px;border-bottom:1px solid var(--line);padding-bottom:9px;margin-bottom:0}}
h2{{font:normal 27px/1.2 Georgia,serif;margin:0}}.aside{{color:var(--muted);font-size:12px}}table{{width:100%;border-collapse:collapse;text-align:left}}
th{{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.5px;font-weight:600;padding:14px 11px}}
td{{border-top:1px solid #edf0f0;padding:15px 11px;vertical-align:middle}}tr:hover td{{background:#fbfcfc}}td:first-child,th:first-child{{padding-left:0}}
.num{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}.up{{color:var(--up);font-weight:700}}.down{{color:var(--down);font-weight:700}}
a{{color:var(--teal);text-decoration:none}}a:hover{{text-decoration:underline}}.minor{{font-size:11px;color:var(--muted);margin-top:4px}}
.empty{{text-align:center;color:var(--muted);padding:32px}}.alert{{border-left:3px solid #b78a4d;background:#fbf8f0;color:#68543c;padding:14px 17px;font-size:13px;margin-bottom:20px}}
.status{{font-size:12px;text-transform:uppercase;font-weight:700}}.ok{{color:var(--up)}}.bad{{color:var(--down)}}
footer{{margin-top:50px;padding-top:20px;border-top:1px solid var(--line);color:var(--muted);font-size:12px;display:flex;justify-content:space-between}}
@media(max-width:780px){{.metrics{{grid-template-columns:repeat(2,1fr)}}.layout{{padding:0 15px 45px}}h1{{font-size:35px}}.tablewrap{{overflow-x:auto}}table{{min-width:700px}}}}
</style></head><body><div class="layout">
<header><div class="brand">Market<span>Signal</span><div class="minor">Autonomous intelligence · Engineering preview</div></div><span class="pill">{status_label}</span></header>
<main><h1>Market intelligence, measured.</h1><p class="lead">An auditable pipeline for detecting consequential prediction-market movements.</p>
{warning}<div class="metrics">
<div class="metric"><strong>{stats["markets"]:,}</strong><span>Markets discovered</span></div>
<div class="metric"><strong>{stats["observations"]:,}</strong><span>Snapshots persisted</span></div>
<div class="metric"><strong>{stats["signals"]:,}</strong><span>Qualified signals</span></div>
<div class="metric"><strong>{stats["failures"]:,}</strong><span>Recorded failures</span></div></div>
<section><div class="sectionhead"><h2>Significant movements</h2><span class="aside">{signals_caption}</span></div>
<div class="tablewrap"><table><thead><tr><th>Contract</th><th class="num">Outcome price</th><th class="num">Change</th><th class="num">Priority</th><th class="num">24h Volume</th></tr></thead>
<tbody>{_signal_rows(data["signals"], is_demo, is_daily)}</tbody></table></div></section>
<section><div class="sectionhead"><h2>Watchlist</h2><span class="aside">Latest stored quotes</span></div>
<div class="tablewrap"><table><thead><tr><th>Contract</th><th class="num">Yes price</th><th class="num">24h volume</th><th class="num">Liquidity</th></tr></thead>
<tbody>{_market_rows(data["markets"])}</tbody></table></div></section>
<section><div class="sectionhead"><h2>Pipeline health</h2><span class="aside">Latest run: {_datetime(last_run["started_at"]) if last_run else "Not yet run"}</span></div>
<div class="tablewrap"><table><thead><tr><th>Run time</th><th>Status</th><th class="num">Saved</th><th class="num">New signals</th></tr></thead>
<tbody>{_run_rows(data["runs"])}</tbody></table></div></section>
</main><footer><span>{footer_label}</span><span>Generated {generated_at}</span></footer></div></body></html>"""
    path = Path(output_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path
