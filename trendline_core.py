"""
Core trendline math — single source of truth, fully vectorized.

Conventions (matching the existing system):
- Prices are analyzed on a LOG scale.
- Slopes are per TRADING DAY (index distance), not calendar days.
- Upper (resistance) line: anchored at the highest high (date1), drawn to the
  later high that produces the LARGEST slope (least negative). Because date1 is
  the global maximum, the max-slope line is mathematically guaranteed not to be
  breached by any intermediate high, so no validation pass is needed.
- Under (support) line: anchored at the lowest low, drawn to the later low that
  produces the SMALLEST slope (least positive) — same guarantee, mirrored.
"""

import numpy as np


def best_upper_trendline(highs):
    """
    Find the upper (resistance) trendline for a series of highs.

    Parameters:
        highs: 1-D array-like of high prices, ordered by trading day.

    Returns:
        (index1, index2, slope) where index1 anchors the highest high,
        index2 is the later point producing the largest log-scale slope,
        or None when no later point exists.
    """
    h = np.asarray(highs, dtype=float)
    n = len(h)
    if n < 2:
        return None

    i1 = int(np.argmax(h))          # first occurrence of the global max
    if i1 >= n - 1:
        return None                  # highest high is the last bar
    if h[i1] <= 0:
        return None                  # garbage data

    later = h[i1 + 1:]
    with np.errstate(divide='ignore', invalid='ignore'):
        slopes = (np.log(later) - np.log(h[i1])) / np.arange(1, n - i1, dtype=float)
    slopes[~np.isfinite(slopes)] = -np.inf   # mask non-positive prices

    rel = int(np.argmax(slopes))
    if not np.isfinite(slopes[rel]):
        return None

    i2 = i1 + 1 + rel
    return i1, i2, float(slopes[rel])


def best_under_trendline(lows):
    """
    Find the under (support) trendline for a series of lows.

    Returns:
        (index1, index2, slope) where index1 anchors the lowest low,
        index2 is the later point producing the smallest log-scale slope,
        or None when no later point exists.
    """
    l = np.asarray(lows, dtype=float)
    n = len(l)
    if n < 2:
        return None

    positive = l > 0
    if not positive.any():
        return None
    # anchor at the first occurrence of the global min among positive prices
    masked = np.where(positive, l, np.inf)
    i1 = int(np.argmin(masked))
    if i1 >= n - 1:
        return None

    later = l[i1 + 1:]
    with np.errstate(divide='ignore', invalid='ignore'):
        slopes = (np.log(later) - np.log(l[i1])) / np.arange(1, n - i1, dtype=float)
    slopes[~np.isfinite(slopes)] = np.inf    # mask non-positive prices

    rel = int(np.argmin(slopes))
    if not np.isfinite(slopes[rel]):
        return None

    i2 = i1 + 1 + rel
    return i1, i2, float(slopes[rel])


def trendline_prices(n_days, anchor_index, anchor_price, slope, decimals=2):
    """
    Project a log-scale trendline across n_days trading days.

    Parameters:
        n_days: total number of trading days to project over (0..n_days-1).
        anchor_index: trading-day index of the anchor point (usually index2).
        anchor_price: price at the anchor point.
        slope: log-scale slope per trading day.

    Returns:
        np.ndarray of trendline prices, rounded to `decimals`.
    """
    offsets = np.arange(n_days, dtype=float) - anchor_index
    return np.round(np.exp(np.log(float(anchor_price)) + slope * offsets), decimals)


def trendline_price_at(target_index, anchor_index, anchor_price, slope, decimals=2):
    """Trendline price at a single trading-day index."""
    return round(float(np.exp(np.log(float(anchor_price)) + slope * (target_index - anchor_index))), decimals)


def calculate_sequence(breakthrough_series):
    """
    Length of the current run of consecutive True values, per position.
    Vectorized equivalent of the original loop implementation.
    """
    b = np.asarray(list(breakthrough_series), dtype=bool)
    if len(b) == 0:
        return []
    idx = np.arange(len(b))
    last_false = np.maximum.accumulate(np.where(~b, idx, -1))
    return ((idx - last_false) * b).astype(int).tolist()


def find_prominent_peaks(highs, prominence_pct=5.0, distance=10):
    """
    Optional utility for anchor research: peaks by prominence instead of the
    single global max. Returns indices of local maxima whose prominence is at
    least `prominence_pct` percent of the price level.

    Not wired into the production pipeline — use it to experiment with
    anchoring trendlines on significant swing highs rather than the
    all-time high only.
    """
    from scipy.signal import find_peaks
    h = np.asarray(highs, dtype=float)
    if len(h) < 3:
        return np.array([], dtype=int)
    peaks, props = find_peaks(h, distance=distance, prominence=h * (prominence_pct / 100.0))
    return peaks
