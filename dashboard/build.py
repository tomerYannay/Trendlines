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
            f'{a("index.html", "מועמדות היום", "index")}{a("wallet.html", "הארנק", "wallet")}'
            f'<span class="stamp">נכון ל-{stamp}</span></nav>')


def page(title, active, stamp, body):
    return ('<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{title}</title><style>{CSS}</style></head><body>'
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


def candidates_table(df, side):
    is_upper = side == 'upper'
    count_col = 'attempt_no' if is_upper else 'touch_no'
    count_lbl = 'ניסיון' if is_upper else 'נגיעה'
    dist_lbl = 'מרחק לקו' if is_upper else 'מעל הקו'
    rows = []
    for _, r in df.iterrows():
        status = r.get('status', '')
        if status == 'מתקרב':
            st = '<span class="chip near">מתקרב</span>'
        else:
            st = f'<span class="chip fresh">אירוע {status[5:] if isinstance(status, str) else status}</span>'
        dist = -r['gap_vs_line_pct'] if is_upper else r['gap_vs_line_pct']
        rows.append(
            f'<tr><td class="tk">{r["ticker"]}</td><td>{st}</td>'
            f'<td class="num">{fmt(r["close"])}</td><td class="num">{fmt(r["line"])}</td>'
            f'<td class="num">{fmt(dist, "{:+.2f}%")}</td>'
            f'<td class="num">{int(r[count_col]) if pd.notna(r.get(count_col)) else "—"}</td>'
            f'<td class="num">{int(r["days_since_anchor"])}</td>'
            f'<td class="num">{fmt(r["slope_yr_pct"], "{:+.1f}%")}</td>'
            f'<td class="num">{fmt(r["vol_ratio20"], "{:.2f}")}</td>'
            f'<td class="num">{fmt(r["atr_pct"], "{:.1f}%")}</td>'
            f'<td class="num">{fmt(r["runup_20d"], "{:+.1f}%")}</td>'
            f'<td class="num">{fmt(r["dollar_vol_m"], "{:.1f}")}</td>'
            f'{conf_cell(r["confidence"])}'
            f'<td class="drivers">{r.get("drivers", "")}</td></tr>'
        )
    return (f'<div class="tablewrap"><table><thead><tr>'
            f'<th>טיקר</th><th>סטטוס</th><th>מחיר</th><th>קו</th><th>{dist_lbl}</th>'
            f'<th>{count_lbl} #</th><th>גיל קו</th><th>שיפוע/שנה</th><th>ווליום יחסי</th>'
            f'<th>ATR</th><th>ראן-אפ 20י</th><th>מחזור $M</th><th>ביטחון</th><th>גורמים מובילים</th>'
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


def build():
    meta = json.load(open('dashboard/data/meta.json'))
    stamp = meta['last_date']
    upper = pd.read_csv('dashboard/data/table_upper.csv')
    under = pd.read_csv('dashboard/data/table_under.csv')
    trades = pd.read_csv('dashboard/data/trades.csv')
    open_pos = pd.read_csv('dashboard/data/open_positions.csv')
    eq = pd.read_csv('dashboard/data/equity.csv')

    os.makedirs(OUT, exist_ok=True)

    # ---------- index ----------
    body = (
        f'<h2>אלכסון עליון — מועמדות לפריצה</h2>'
        f'<p class="lede">אירועי פריצה מהימים האחרונים + מניות במרחק עד 3% מתחת לקו. '
        f'כניסות הארנק דורשות ניסיון 2+, מחיר ≥ $5 וביטחון ≥ 55%.</p>'
        + candidates_table(upper, 'upper') +
        f'<h2>אלכסון תחתון — מועמדות לקפיצת תמיכה</h2>'
        f'<p class="lede">נגיעות תמיכה מהימים האחרונים + מניות במרחק עד 3% מעל הקו. '
        f'כניסות הארנק דורשות קו בוגר 50+ יום, שיפוע שפוי וביטחון ≥ 55%.</p>'
        + candidates_table(under, 'under') +
        f'<p class="foot">הקווים מעוגנים על דאטה עד {meta["as_of"]} ומתעדכנים לפי כללי החידוש המאומתים '
        f'(200 יום / 100% / כישלון עמוק). ביטחון = הסתברות מכוילת ל-20 ימי מסחר חיוביים, '
        f'ממודל שאומן על 49,034 אירועים 2022–2026. עדכון: python -m dashboard.daily</p>'
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

    body = (
        f'<h2>הארנק הדיגיטלי — סימולציית ההמלצות</h2>'
        f'<p class="lede">כל כניסה: $5,000 · סטופ ‎-10% · טייק +20% · יציאת זמן אחרי 40 ימי מסחר · '
        f'מקס׳ 20 פוזיציות. נכנס אוטומטית לכל איתות שעומד בכללים המאומתים.</p>'
        + tiles + equity_svg(eq) +
        f'<h2>פוזיציות פתוחות ({len(open_pos)})</h2>'
        f'<div class="tablewrap"><table><thead><tr><th>טיקר</th><th>סוג</th><th>כניסה</th>'
        f'<th>מחיר כניסה</th><th>אחרון</th><th>רווח/הפסד</th><th>SL</th><th>TP</th><th>ימים</th><th>ביטחון</th>'
        f'</tr></thead><tbody>{op_rows}</tbody></table></div>'
        f'<h2>יומן עסקאות ({len(trades)})</h2>'
        f'<div class="tablewrap"><table><thead><tr><th>טיקר</th><th>סוג</th><th>כניסה</th><th>יציאה</th>'
        f'<th>מחיר כניסה</th><th>מחיר יציאה</th><th>סיבה</th><th>%</th><th>$</th><th>ימים</th><th>ביטחון</th>'
        f'</tr></thead><tbody>{tr_rows}</tbody></table></div>'
        f'<p class="foot">קו מקווקו בגרף = הון התחלתי $100,000. הסימולציה דטרמיניסטית ומחושבת מחדש '
        f'מ-{meta["as_of"]} בכל עדכון יומי — המספרים תמיד נכונים לתאריך שבכותרת.</p>'
    )
    with open(f'{OUT}/wallet.html', 'w', encoding='utf-8') as f:
        f.write(page('Trendlines — הארנק', 'wallet', stamp, body))

    print(f"site built: {OUT}/index.html, {OUT}/wallet.html (as of {stamp})")


if __name__ == '__main__':
    build()
