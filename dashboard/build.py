"""
Static site generator for the Trendlines dashboard.

Reads dashboard/data/*.csv (produced by dashboard.engine) and writes two
self-contained pages to dashboard/site/:
  index.html  — today's candidates: upper-diagonal table + support table
  wallet.html — the paper wallet: equity curve, open positions, trade log

Usage:  python -m dashboard.build
"""
import json
import os

import pandas as pd

OUT = 'dashboard/site'

CSS = """
  :root {
    --paper:#FBFAF7; --ink:#232D34; --ink2:#5B6A73; --ink3:#8A969D; --line:#E4E1D8;
    --card:#FFFFFF; --under:#0B8975; --upper:#C25E10; --under-soft:#E3F1EE;
    --upper-soft:#F7EADD; --danger:#A8323C; --danger-soft:#F6E7E8; --good-soft:#E3F1EE;
  }
  @media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
    --paper:#14191E; --ink:#E4E8EA; --ink2:#9AA7AE; --ink3:#6E7B82; --line:#2A333A;
    --card:#1B2229; --under:#12A088; --upper:#C97F35; --under-soft:#17332E;
    --upper-soft:#362A1B; --danger:#D06670; --danger-soft:#3A2226; --good-soft:#17332E;
  } }
  :root[data-theme="dark"] {
    --paper:#14191E; --ink:#E4E8EA; --ink2:#9AA7AE; --ink3:#6E7B82; --line:#2A333A;
    --card:#1B2229; --under:#12A088; --upper:#C97F35; --under-soft:#17332E;
    --upper-soft:#362A1B; --danger:#D06670; --danger-soft:#3A2226; --good-soft:#17332E;
  }
  * { box-sizing:border-box; }
  body { background:var(--paper); color:var(--ink); font-family:system-ui,-apple-system,"Segoe UI",sans-serif;
         margin:0; padding:28px 20px 70px; line-height:1.55; }
  .wrap { max-width:1180px; margin:0 auto; }
  nav { display:flex; gap:8px; align-items:baseline; border-bottom:2px solid var(--ink);
        padding-bottom:14px; margin-bottom:22px; flex-wrap:wrap; }
  nav .brand { font-size:20px; font-weight:750; margin-inline-end:14px; }
  nav a { color:var(--ink2); text-decoration:none; font-size:14px; font-weight:600;
          padding:4px 12px; border-radius:4px; }
  nav a.active { background:var(--ink); color:var(--paper); }
  nav .stamp { margin-inline-start:auto; color:var(--ink3); font-size:12.5px; }
  h2 { font-size:19px; margin:26px 0 4px; }
  .lede { color:var(--ink2); font-size:13px; margin:0 0 12px; }
  .num { font-variant-numeric:tabular-nums; }
  .tablewrap { overflow-x:auto; border:1px solid var(--line); border-radius:6px; background:var(--card); }
  table { border-collapse:collapse; width:100%; font-size:12.8px; min-width:900px; }
  th { text-align:right; font-size:11px; letter-spacing:.04em; color:var(--ink2);
       border-bottom:1px solid var(--line); padding:8px 10px; font-weight:650; white-space:nowrap;
       position:sticky; top:0; background:var(--card); }
  td { padding:6px 10px; border-bottom:1px solid var(--line); white-space:nowrap; }
  tr:last-child td { border-bottom:none; }
  td.tk { font-weight:700; }
  .chip { display:inline-block; font-size:10px; font-weight:700; border-radius:3px; padding:1px 6px; }
  .chip.fresh { background:var(--upper-soft); color:var(--upper); }
  .chip.near { background:var(--under-soft); color:var(--under); }
  .chip.warn { background:var(--danger-soft); color:var(--danger); }
  .chip.appr { background:transparent; border:1px dashed var(--ink3); color:var(--ink2); }
  .chip.side-u { background:var(--upper-soft); color:var(--upper); }
  .chip.side-s { background:var(--under-soft); color:var(--under); }
  .conf { font-weight:750; }
  .conf.hi { color:var(--under); }
  .conf.lo { color:var(--ink3); }
  .pnl-pos { color:var(--under); font-weight:650; }
  .pnl-neg { color:var(--danger); font-weight:650; }
  .drivers { color:var(--ink3); font-size:11px; }
  .tiles { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:10px; margin:14px 0 20px; }
  .tile { background:var(--card); border:1px solid var(--line); border-radius:6px; padding:12px 14px; }
  .tile .t { font-size:11px; color:var(--ink2); font-weight:650; letter-spacing:.05em; }
  .tile .v { font-size:24px; font-weight:750; margin-top:2px; }
  .chart { background:var(--card); border:1px solid var(--line); border-radius:6px; padding:14px; margin-bottom:20px; }
  .foot { margin-top:34px; color:var(--ink3); font-size:12px; }
"""


def nav(active, stamp):
    a = lambda href, name, key: f'<a href="{href}" class="{"active" if active == key else ""}">{name}</a>'
    return (f'<nav><span class="brand">📐 Trendlines</span>'
            f'{a("index.html", "מועמדות", "index")}{a("wallet.html", "הארנק", "wallet")}'
            f'<span class="stamp">נתוני שוק עדכניים ל-<b>{stamp}</b></span></nav>')


def staleness_banner(meta):
    import datetime
    import numpy as np
    run_at = pd.Timestamp(meta.get('run_at', datetime.datetime.now().isoformat()))
    data_date = pd.Timestamp(meta['last_date'])
    # business-day gap: warns from one missed trading day, quiet over weekends
    bgap = int(np.busday_count(data_date.date(), run_at.date()))
    if bgap > 1:
        return (f'<div style="background:var(--danger-soft);border:1px solid var(--danger);color:var(--danger);'
                f'border-radius:6px;padding:10px 14px;font-size:13px;font-weight:600;margin-bottom:14px">'
                f'⚠️ הדאטה אינו עדכני: יום המסחר האחרון שנקלט הוא {meta["last_date"]} '
                f'({bgap} ימי מסחר לפני מועד הריצה). הרץ python -m dashboard.daily לרענון.</div>')
    return ''


def page(title, active, stamp, body):
    return ('<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{title}</title><style>{CSS}{TOGGLE_CSS}</style></head><body>'
            f'<div class="wrap">{nav(active, stamp)}{body}</div></body></html>')


def fmt(v, pat='{:.2f}', dash='—'):
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return dash
        return pat.format(float(v))
    except (TypeError, ValueError):
        return dash


def conf_cell(v):
    if v is None or pd.isna(v):
        return '<td class="num">—</td>'
    cls = 'hi' if v >= 55 else ('lo' if v < 50 else '')
    return f'<td class="num conf {cls}">{v:.1f}%</td>'


STATUS_CHIPS = {
    'BREAKOUT': ('fresh', 'פריצה'),
    'SUPPORT_TOUCH': ('near', 'נגיעת תמיכה'),
    'PIERCED': ('warn', 'חדירה — טרם אושרה'),
    'APPROACHING': ('appr', 'מתקרב'),
}


def candidates_table(df, side):
    is_upper = side == 'upper'
    count_col = 'attempt_no' if is_upper else 'touch_no'
    count_lbl = 'ניסיון' if is_upper else 'נגיעה'
    dist_lbl = 'מרחק לקו' if is_upper else 'מעל הקו'
    a1_lbl, a2_lbl = ('H1', 'H2') if is_upper else ('L1', 'L2')
    rows = []
    for _, r in df.iterrows():
        status = r.get('status', 'APPROACHING')
        cls, lbl = STATUS_CHIPS.get(status, ('appr', status))
        date_txt = ''
        if status != 'APPROACHING' and pd.notna(r.get('event_date')):
            date_txt = f' {str(r["event_date"])[5:]}'
        st = f'<span class="chip {cls}">{lbl}{date_txt}</span>'
        dist = -r['gap_vs_line_pct'] if is_upper else r['gap_vs_line_pct']
        if status == 'APPROACHING':
            conf_td = '<td class="num" title="הסתברות מוצגת רק לאירוע בפועל — המודל אומן על אירועים, לא על התקרבויות">—</td>'
            exp_td = '<td class="num">—</td>'
        else:
            conf_td = conf_cell(r['confidence'])
            exp_td = f'<td class="num">{fmt(r.get("expected_ret_20d"), "{:+.1f}%")}</td>'
        a1 = str(r.get('anchor1', ''))[:10] if pd.notna(r.get('anchor1')) else '—'
        a2 = str(r.get('anchor2', ''))[:10] if pd.notna(r.get('anchor2')) else '—'
        rows.append(
            f'<tr><td class="tk">{r["ticker"]}</td><td>{st}</td>'
            f'<td class="num">{fmt(r["close"])}</td><td class="num">{fmt(r["line"])}</td>'
            f'<td class="num">{a1}</td><td class="num">{a2}</td>'
            f'<td class="num">{fmt(dist, "{:+.2f}%")}</td>'
            f'<td class="num">{int(r[count_col]) if pd.notna(r.get(count_col)) else "—"}</td>'
            f'<td class="num">{int(r["days_since_anchor"])}</td>'
            f'<td class="num">{fmt(r["slope_yr_pct"], "{:+.1f}%")}</td>'
            f'<td class="num">{fmt(r["vol_ratio20"], "{:.2f}")}</td>'
            f'<td class="num">{fmt(r["atr_pct"], "{:.1f}%")}</td>'
            f'<td class="num">{fmt(r["runup_20d"], "{:+.1f}%")}</td>'
            f'<td class="num">{fmt(r["dollar_vol_m"], "{:.1f}")}</td>'
            f'{conf_td}{exp_td}'
            f'<td class="drivers">{r.get("drivers", "") if status != "APPROACHING" else ""}</td></tr>'
        )
    return (f'<div class="tablewrap"><table><thead><tr>'
            f'<th>טיקר</th><th>סטטוס</th><th>מחיר</th><th>קו</th>'
            f'<th>{a1_lbl}</th><th>{a2_lbl}</th><th>{dist_lbl}</th>'
            f'<th>{count_lbl} #</th><th>גיל קו</th><th>שיפוע/שנה</th><th>ווליום יחסי</th>'
            f'<th>ATR</th><th>ראן-אפ 20י</th><th>מחזור $M</th><th>ביטחון</th><th>תוחלת 20י</th><th>גורמים מובילים</th>'
            f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>')


def equity_svg(eq):
    if eq.empty:
        return ''
    vals = eq['equity'].astype(float).values
    n = len(vals)
    w, h = 1080, 260
    lo, hi = vals.min() * 0.995, vals.max() * 1.005
    xs = [i * (w - 70) / max(1, n - 1) + 60 for i in range(n)]
    ys = [h - 30 - (v - lo) / (hi - lo) * (h - 55) for v in vals]
    pts = ' '.join(f'{x:.1f},{y:.1f}' for x, y in zip(xs, ys))
    area = f'M {xs[0]:.1f},{h - 30} L {pts.replace(" ", " L ")} L {xs[-1]:.1f},{h - 30} Z'
    base_y = h - 30 - (100000 - lo) / (hi - lo) * (h - 55) if lo < 100000 < hi else None
    base = (f'<line x1="60" x2="{w - 10}" y1="{base_y:.1f}" y2="{base_y:.1f}" stroke="var(--ink3)" '
            f'stroke-dasharray="4 4" stroke-width="1"/>' if base_y else '')
    labels = ''
    for frac in (0, 0.5, 1):
        v = lo + (hi - lo) * frac
        y = h - 30 - frac * (h - 55)
        labels += (f'<text x="52" y="{y + 4:.1f}" text-anchor="end" font-size="11" fill="var(--ink2)" '
                   f'class="num">{v / 1000:,.0f}k</text>')
    d0, d1 = eq['date'].iloc[0], eq['date'].iloc[-1]
    return (f'<div class="chart"><svg viewBox="0 0 {w} {h}" style="width:100%;height:auto" role="img" '
            f'aria-label="עקומת הון">'
            f'<path d="{area}" fill="var(--under)" opacity="0.10"/>'
            f'{base}<polyline points="{pts}" fill="none" stroke="var(--under)" stroke-width="2"/>'
            f'<circle cx="{xs[-1]:.1f}" cy="{ys[-1]:.1f}" r="4" fill="var(--under)"/>'
            f'{labels}'
            f'<text x="60" y="{h - 8}" font-size="11" fill="var(--ink2)">{d0}</text>'
            f'<text x="{w - 10}" y="{h - 8}" text-anchor="end" font-size="11" fill="var(--ink2)">{d1}</text>'
            f'</svg></div>')


def read_csv_safe(path, columns):
    try:
        return pd.read_csv(path)
    except (pd.errors.EmptyDataError, FileNotFoundError):
        return pd.DataFrame(columns=columns)


TOGGLE_CSS = """
  .uni-toggle { display:flex; gap:6px; margin:4px 0 18px; }
  .uni-toggle button { font:inherit; font-size:13.5px; font-weight:700; padding:7px 18px; border-radius:5px;
    border:1px solid var(--line); background:var(--card); color:var(--ink2); cursor:pointer; }
  .uni-toggle button.on { background:var(--ink); color:var(--paper); border-color:var(--ink); }
  .uni-toggle button:focus-visible { outline:2px solid var(--under); outline-offset:2px; }
  .universe { display:none; }
  .universe.on { display:block; }
"""

TOGGLE_JS = """
<script>
function showUni(key) {
  document.querySelectorAll('.universe').forEach(d => d.classList.toggle('on', d.dataset.uni === key));
  document.querySelectorAll('.uni-toggle button').forEach(b => b.classList.toggle('on', b.dataset.uni === key));
  try { localStorage.setItem('trendlines_universe', key); } catch (e) {}
}
document.addEventListener('DOMContentLoaded', () => {
  let k = 'russell';
  try { k = localStorage.getItem('trendlines_universe') || 'russell'; } catch (e) {}
  if (!document.querySelector(`.universe[data-uni="${k}"]`)) k = 'russell';
  showUni(k);
});
</script>
"""


def universe_section(key, label, meta_u, upper, under, watch_only_note=''):
    return (
        f'<div class="universe" data-uni="{key}">'
        f'{watch_only_note}'
        f'<h2>אלכסון עליון — מועמדות לפריצה ({len(upper)})</h2>'
        f'<p class="lede">אירועי פריצה מהימים האחרונים + מניות במרחק עד 3% מתחת לקו.</p>'
        + candidates_table(upper, 'upper') +
        f'<h2>אלכסון תחתון — מועמדות לקפיצת תמיכה ({len(under)})</h2>'
        f'<p class="lede">נגיעות תמיכה מהימים האחרונים + מניות במרחק עד 3% מעל הקו.</p>'
        + candidates_table(under, 'under') +
        f'</div>'
    )


def build():
    meta = json.load(open('dashboard/data/meta.json'))
    stamp = meta['last_date']
    trades = read_csv_safe('dashboard/data/trades.csv',
                           ['ticker', 'side', 'entry_date', 'exit_date', 'entry', 'exit', 'reason',
                            'pnl', 'pnl_pct', 'days_held', 'sl', 'tp', 'confidence'])
    open_pos = read_csv_safe('dashboard/data/open_positions.csv',
                             ['ticker', 'side', 'entry_date', 'entry', 'last', 'pnl_pct',
                              'sl', 'tp', 'days_held', 'confidence'])
    eq = read_csv_safe('dashboard/data/equity.csv', ['date', 'equity', 'open_positions', 'cash'])

    os.makedirs(OUT, exist_ok=True)

    # ---------- index ----------
    banner = staleness_banner(meta)
    universes = meta.get('universes', {})
    toggle_btns = ''.join(
        f'<button data-uni="{k}" onclick="showUni(\'{k}\')">{u["label"]}</button>'
        for k, u in universes.items())
    sections = ''
    for k, u in universes.items():
        upper_u = read_csv_safe(f'dashboard/data/table_upper_{k}.csv',
                                ['ticker', 'status', 'close', 'line', 'gap_vs_line_pct', 'confidence'])
        under_u = read_csv_safe(f'dashboard/data/table_under_{k}.csv',
                                ['ticker', 'status', 'close', 'line', 'gap_vs_line_pct', 'confidence'])
        note = ''
        if k != meta.get('wallet_universe'):
            note = (f'<div style="border:1px dashed var(--ink3);color:var(--ink2);border-radius:6px;'
                    f'padding:8px 14px;font-size:12.5px;margin-bottom:6px">👁️ יקום צפייה בלבד — הארנק אינו נכנס '
                    f'לעסקאות כאן, וציוני הביטחון הם העברה של מודל שאומן על ראסל וטרם אומתו על מדד זה.</div>')
        sections += universe_section(k, u['label'], u, upper_u, under_u, note)

    body = (
        banner +
        f'<div class="uni-toggle">{toggle_btns}</div>'
        + sections +
        f'<p class="foot">הקווים מעוגנים על דאטה עד {meta["as_of"]} ומתעדכנים לפי כללי החידוש המאומתים '
        f'(200 יום / 100% / כישלון עמוק). ביטחון = הסתברות מכוילת ל-20 ימי מסחר חיוביים, מוצגת לאירועים בפועל בלבד; '
        f'מודל {meta.get("mode","")} קפוא שאומן עד {meta.get("model_fit_through","")} וכויל עד {meta.get("model_calibrated_through","")}. '
        f'תוחלת 20י = תשואה ממוצעת היסטורית בדלי הקליברציה — מדד נפרד מההסתברות. '
        f'כניסות הארנק (ראסל בלבד): ניסיון 2+/תמיכה בוגרת, מחיר ≥ $5, ביטחון ≥ 55%. עדכון: python -m dashboard.daily</p>'
        + TOGGLE_JS
    )
    with open(f'{OUT}/index.html', 'w', encoding='utf-8') as f:
        f.write(page('Trendlines — מועמדות היום', 'index', stamp, body))

    # ---------- wallet ----------
    total_pnl = trades['pnl'].sum() if len(trades) else 0
    open_val = len(open_pos) * 5000
    final_eq = eq['equity'].iloc[-1] if len(eq) else 100000
    ret_pct = (final_eq / 100000 - 1) * 100
    win = (trades['pnl'] > 0).mean() * 100 if len(trades) else 0
    tiles = f"""
    <div class="tiles">
      <div class="tile"><div class="t">שווי הארנק</div><div class="v num">${final_eq:,.0f}</div></div>
      <div class="tile"><div class="t">תשואה כוללת</div><div class="v num {'pnl-pos' if ret_pct >= 0 else 'pnl-neg'}">{ret_pct:+.2f}%</div></div>
      <div class="tile"><div class="t">עסקאות סגורות</div><div class="v num">{len(trades)}</div></div>
      <div class="tile"><div class="t">אחוז הצלחה</div><div class="v num">{win:.1f}%</div></div>
      <div class="tile"><div class="t">פוזיציות פתוחות</div><div class="v num">{len(open_pos)}</div></div>
    </div>"""

    def side_chip(s):
        return f'<span class="chip {"side-u" if s == "פריצה" else "side-s"}">{s}</span>'

    op_rows = ''.join(
        f'<tr><td class="tk">{r["ticker"]}</td><td>{side_chip(r["side"])}</td>'
        f'<td class="num">{r["entry_date"]}</td><td class="num">{fmt(r["entry"])}</td>'
        f'<td class="num">{fmt(r["last"])}</td>'
        f'<td class="num {"pnl-pos" if r["pnl_pct"] >= 0 else "pnl-neg"}">{r["pnl_pct"]:+.2f}%</td>'
        f'<td class="num">{fmt(r["sl"])}</td><td class="num">{fmt(r["tp"])}</td>'
        f'<td class="num">{int(r["days_held"])}</td>{conf_cell(r["confidence"])}</tr>'
        for _, r in open_pos.iterrows())

    tr_sorted = trades.sort_values('exit_date', ascending=False) if len(trades) else trades
    tr_rows = ''.join(
        f'<tr><td class="tk">{r["ticker"]}</td><td>{side_chip(r["side"])}</td>'
        f'<td class="num">{r["entry_date"]}</td><td class="num">{r["exit_date"]}</td>'
        f'<td class="num">{fmt(r["entry"])}</td><td class="num">{fmt(r["exit"])}</td>'
        f'<td>{r["reason"]}</td>'
        f'<td class="num {"pnl-pos" if r["pnl"] >= 0 else "pnl-neg"}">{r["pnl_pct"]:+.2f}%</td>'
        f'<td class="num {"pnl-pos" if r["pnl"] >= 0 else "pnl-neg"}">${r["pnl"]:+,.0f}</td>'
        f'<td class="num">{int(r["days_held"])}</td>{conf_cell(r["confidence"])}</tr>'
        for _, r in tr_sorted.iterrows())

    issues = meta.get('data_issues', [])
    issues_html = ''
    if issues:
        items = ''.join(f'<li>{i}</li>' for i in issues)
        issues_html = (f'<h2>בעיות דאטה שטופלו</h2><div class="tablewrap" style="padding:10px 16px">'
                       f'<ul style="margin:6px 0;padding-inline-start:18px;font-size:13px">{items}</ul></div>')
    qmeta = meta.get('quality', {})
    q_closed = read_csv_safe('dashboard/data/quality_trades.csv',
                             ['ticker', 'rule', 'entry_date', 'entry', 'status', 'reason',
                              'ret_pct', 'days', 'exit_date', 'stop_today', 'pnl'])
    q_open = read_csv_safe('dashboard/data/quality_open.csv',
                           ['ticker', 'rule', 'entry_date', 'entry', 'status', 'reason',
                            'ret_pct', 'days', 'exit_date', 'stop_today', 'pnl'])
    q_eq = read_csv_safe('dashboard/data/quality_equity.csv', ['date', 'equity'])
    q_tiles = ''
    if len(q_closed) or len(q_open):
        q_end = qmeta.get('equity_end', 100000)
        q_ret = qmeta.get('ret_pct', 0)
        q_tiles = f'''
        <div class="tiles">
          <div class="tile"><div class="t">שווי הארנק</div><div class="v num">${q_end:,.0f}</div></div>
          <div class="tile"><div class="t">תשואה כוללת</div>
            <div class="v num {'pnl-pos' if q_ret >= 0 else 'pnl-neg'}">{q_ret:+.2f}%</div></div>
          <div class="tile"><div class="t">עסקאות סגורות</div><div class="v num">{len(q_closed)}</div></div>
          <div class="tile"><div class="t">אחוז הצלחה</div><div class="v num">{qmeta.get('win_pct') or 0}%</div></div>
          <div class="tile"><div class="t">פוזיציות פתוחות</div><div class="v num">{len(q_open)}</div></div>
        </div>''' + equity_svg(q_eq)
    def q_row(r, is_open):
        pnl_cls = 'pnl-pos' if (r['ret_pct'] or 0) >= 0 else 'pnl-neg'
        tail = (f'<td class="num">{fmt(r["stop_today"])}</td>' if is_open
                else f'<td class="num">{r["exit_date"]}</td><td>{r["reason"]}</td>')
        return (f'<tr><td class="tk">{r["ticker"]}</td>'
                f'<td><span class="chip near">{r["rule"]}</span></td>'
                f'<td class="num">{r["entry_date"]}</td><td class="num">{fmt(r["entry"])}</td>'
                f'<td class="num {pnl_cls}">{(r["ret_pct"] or 0):+.2f}%</td>'
                f'<td class="num">{int(r["days"])}</td>{tail}</tr>')
    q_open_rows = ''.join(q_row(r, True) for _, r in q_open.iterrows())
    q_closed_recent = q_closed.sort_values('exit_date', ascending=False).head(25)
    q_closed_rows = ''.join(q_row(r, False) for _, r in q_closed_recent.iterrows())
    quality_html = ''
    if len(q_closed) or len(q_open):
        quality_html = (
            f'<h2 style="margin-top:48px">אסטרטגיה 2 — ארנק האיכות '
            f'<span class="chip near">תמיכות בלבד · שער N1/N2/N3 · סטופ קו−ATR · עד 90 יום</span></h2>'
            f'<p class="lede">המפרט הוקפא על 2020–2023 ונבחן על 2024–2026 (+3.14% לעסקה מול +1.22% ללא שער). '
            f'מ-{qmeta.get("start","2024-01-01")}; מהיום — LIVE_FORWARD. פרופיל: ~25% הצלחה עם זנב ימני גדול — לא להיבהל מרצפי סטופים.</p>'
            + q_tiles +
            f'<h3 style="font-size:15px;margin:18px 0 6px">פוזיציות פתוחות ({len(q_open)})</h3>'
            f'<div class="tablewrap"><table><thead><tr><th>טיקר</th><th>כלל</th><th>כניסה</th>'
            f'<th>מחיר</th><th>רווח/הפסד</th><th>ימים</th><th>סטופ נוכחי (קו−ATR)</th></tr></thead>'
            f'<tbody>{q_open_rows}</tbody></table></div>'
            f'<h3 style="font-size:15px;margin:18px 0 6px">עסקאות אחרונות ({len(q_closed)} סה"כ, 25 אחרונות)</h3>'
            f'<div class="tablewrap"><table><thead><tr><th>טיקר</th><th>כלל</th><th>כניסה</th>'
            f'<th>מחיר</th><th>%</th><th>ימים</th><th>יציאה</th><th>סיבה</th></tr></thead>'
            f'<tbody>{q_closed_rows}</tbody></table></div>')
    body = (
        staleness_banner(meta) +
        f'<p class="lede" style="font-size:14px"><b>שני ארנקים וירטואליים עצמאיים</b>, לכל אחד $100,000 משלו, כללי כניסה ויציאה שונים ואותו פורמט דיווח — כדי להשוות ראש-בראש איזו גישה מנצחת בזמן אמת.</p>'
        f'<h2>אסטרטגיה 1 — ארנק הביטחון <span class="chip warn">OUT-OF-SAMPLE — מודל קפוא</span></h2>'
        f'<p class="lede">יקום: <b>ראסל 2000 בלבד</b> (שם ה-edge אומת; S&P לצפייה בלבד) · כל כניסה: $5,000 · סטופ ‎-10% · '
        f'טייק +20% · יציאת זמן אחרי 40 ימי מסחר · מקס׳ 20 פוזיציות.</p>'
        + tiles + equity_svg(eq) +
        f'<h2>פוזיציות פתוחות ({len(open_pos)})</h2>'
        f'<div class="tablewrap"><table><thead><tr><th>טיקר</th><th>סוג</th><th>כניסה</th>'
        f'<th>מחיר כניסה</th><th>אחרון</th><th>רווח/הפסד</th><th>SL</th><th>TP</th><th>ימים</th><th>ביטחון</th>'
        f'</tr></thead><tbody>{op_rows}</tbody></table></div>'
        f'<h2>יומן עסקאות ({len(trades)})</h2>'
        f'<div class="tablewrap"><table><thead><tr><th>טיקר</th><th>סוג</th><th>כניסה</th><th>יציאה</th>'
        f'<th>מחיר כניסה</th><th>מחיר יציאה</th><th>סיבה</th><th>%</th><th>$</th><th>ימים</th><th>ביטחון</th>'
        f'</tr></thead><tbody>{tr_rows}</tbody></table></div>'
        + quality_html + issues_html +
        f'<p class="foot">קו מקווקו בגרף = הון התחלתי $100,000. הסימולציה דטרמיניסטית ומחושבת מחדש '
        f'מ-{meta["as_of"]} בכל עדכון יומי. הארנק ההיסטורי הוא שחזור OUT_OF_SAMPLE: המודל אומן וכויל רק על מידע שקדם '
        f'ל-{meta["as_of"]}; ביצועים מ-{meta.get("run_at","")[:10]} ואילך הם LIVE_FORWARD.</p>'
    )
    with open(f'{OUT}/wallet.html', 'w', encoding='utf-8') as f:
        f.write(page('Trendlines — הארנק', 'wallet', stamp, body))

    print(f"site built: {OUT}/index.html, {OUT}/wallet.html (as of {stamp})")


if __name__ == '__main__':
    build()
