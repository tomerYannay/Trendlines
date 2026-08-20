# Diago — Promo Film Narration Script

Video: `diago_promo.mp4` · 88 seconds · 1280×720 · silent (narration added by your tool)

Two versions below — **English** (matches the on-screen text; recommended for the
global audience) and **עברית** (identical timing). Pace ≈ 2.2–2.5 words/second;
each block fits its window with breathing room. Direction notes in [brackets]
are for the narrator, not to be read.

---

## English narration (timecoded)

**00:00 – 00:09 · Scene 1: The hook** *(a diagonal line draws across a dark screen)*
> Every stock chart hides a line.
> Connect the highs, or the lows — and you get a diagonal.
> When price breaks it… things happen.

**00:10 – 00:21 · Scene 2: The problem** *(a wall of 28 mini-charts, then blackout)*
> There are more than two thousand stocks worth watching.
> [beat]
> You can't watch them all. Nobody can.

**00:22 – 00:40 · Scene 3: The breakout** *(candles build, the line draws, breakout, alert pops)*
> This is Diago. Every night it redraws the trendlines of two thousand two hundred and fifty-nine stocks.
> [pause while the line draws]
> And the moment a stock closes above its diagonal —
> [breakout candle glows]
> you get the alert. With a score.

**00:41 – 00:55 · Scene 4: The support bounce** *(rally, plunge back to the line, bounce, alert)*
> It works the other way too.
> A stock falls hard — all the way back to its rising support line…
> [bounce glows]
> holds it, and bounces. That's Diago's strongest setup.

**00:56 – 01:11 · Scene 5: Proof** *(score card, checkmarks, performance table with losers)*
> Every signal gets a confidence score — calibrated on seventy-two thousand historical setups.
> And every signal is tracked, publicly, from the day it prints.
> Winners… and losers. Nothing deleted. Ever.

**01:12 – 01:28 · Scene 6: The offer** *(warm brand screen, logo, price)*
> Diago. Your ranked shortlist, ready every morning before the market opens.
> Seven days free. Then five dollars a month.
> [softer, faster — legal tone]
> Simulated results. Statistics, not promises. Never investment advice.

---

## קריינות בעברית (אותם טיימקודים)

**00:00 – 00:09 · סצנה 1: הפתיח**
> בכל גרף של מניה מסתתר קו.
> חבר את השיאים, או את השפלים — ותקבל אלכסון.
> וכשהמחיר שובר אותו… דברים קורים.

**00:10 – 00:21 · סצנה 2: הבעיה**
> יש יותר מאלפיים מניות ששווה לעקוב אחריהן.
> [שנייה של שקט]
> אי אפשר לעקוב אחרי כולן. אף אחד לא יכול.

**00:22 – 00:40 · סצנה 3: הפריצה**
> זה דיאגו. כל לילה הוא משרטט מחדש את קווי המגמה של אלפיים מאתיים חמישים ותשע מניות.
> [השהיה בזמן שהקו נמתח]
> וברגע שמניה סוגרת מעל האלכסון שלה —
> [נר הפריצה זוהר]
> אתה מקבל את ההתראה. עם ציון.

**00:41 – 00:55 · סצנה 4: הבאונס מהתמיכה**
> זה עובד גם בכיוון השני.
> מניה נופלת חזק — עד קו התמיכה העולה שלה…
> [הבאונס זוהר]
> מחזיקה אותו, וקופצת. זה הסטאפ החזק ביותר של דיאגו.

**00:56 – 01:11 · סצנה 5: הוכחה**
> כל איתות מקבל ציון ביטחון — מכויל על שבעים ושניים אלף סטאפים היסטוריים.
> וכל איתות נמדד, בפומבי, מהיום שבו נולד.
> מנצחים… ומפסידים. שום דבר לא נמחק. אף פעם.

**01:12 – 01:28 · סצנה 6: ההצעה**
> דיאגו. רשימה מדורגת, מוכנה כל בוקר לפני פתיחת המסחר.
> שבעה ימים חינם. אחר כך חמישה דולר בחודש.
> [טון מהיר ורך יותר]
> תוצאות מדומות. סטטיסטיקה, לא הבטחות. לעולם לא ייעוץ השקעות.

---

## Production notes

- **Sync anchors** (exact moments worth hitting): line finishes drawing 00:31,
  breakout glow 00:32.7, breakout alert pops 00:35.1, support bounce glow 00:49.1,
  support alert 00:51.1, score card lands 00:57.6, "losers" table row (PARA −94%)
  00:66.5, price pill 01:19.
- Music: something minimal/pulsing, duck −6dB under narration; a soft riser into
  00:32 (breakout) and 00:49 (bounce) lands well.
- To re-record visuals or change pacing: edit `product/promo/make_film.py`
  (scene times are plain seconds), then `python3 -m product.promo.make_film`
  and `python3 -m product.promo.render_film`.
- `film.html` also plays in any browser (one 88s run) if you prefer to
  screen-record instead of using the MP4.
