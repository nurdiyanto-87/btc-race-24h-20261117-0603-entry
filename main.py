"""Fast EMA breakout bot for the make.fun btc-race 24h bounty.

Trades Coinbase Wrapped BTC (CBBTC) against USDC on one-minute bars, long
only, starting from 1,000 USDC of paper money. Speaks
agent-fun/bars-replay/v1 through the kit's Python shim (vendored unchanged
under vendor/).

Idea
----
On one-minute bars BTC mostly chops sideways: the 1-minute return has a
standard deviation of only ~6 bps on the dev window, while a full-size
round trip costs ~26 bps in fees, slippage and price impact. A bot that
trades every crossover bleeds on whipsaws, and a bot that waits for a slow
trend never trades at all. This bot therefore waits for one sharp,
confirmed break and then rides it:

  * Entry, full equity: the EMA(8) of closes crosses above the EMA(13)
    AND the trailing 15-minute return is above +0.45%. The cross alone
    fires constantly in chop; the 15-minute confirmation asks that the
    price has actually moved, not just that two averages drifted past
    each other. The confirmation window is short on purpose: on the dev
    window the one real break (a +1.3% hour) builds in about fifteen
    minutes, and a 30- or 60-minute confirmation arrives after the move
    is half over.
  * Exit, whole position: the EMA(8) crosses back below the EMA(13)
    (the trend is gone) — but not within 10 bars of entry, where a
    cross-down is one-minute noise and an instant exit would lock in
    the ~26 bps round-trip cost for nothing — or the position falls
    0.75% below the highest value it reached since entry (a trailing
    stop that banks the move when momentum rolls over before the
    averages cross back, and that stays live during the 10-bar hold
    so a real drop still gets out immediately). No fixed
    take-profit: the one dev-window trade gained 0.45% and was still
    rising when the cross-down fired; capping the upside at an arbitrary
    level throws away the tail the bot is built to catch.
  * A buy caps its slippage at 200 bps past the close it was decided
    on; a sell leaves it wide open (10,000 bps) so an exit always
    executes instead of being refused into a falling market.

Why these numbers: on the dev window this configuration makes one round
trip, +$4.42 net after every fee, with 0.95% maximum drawdown. The
neighbouring settings all land on the same trade (EMA 8/13 with a
15- or 20-minute confirmation at +0.30% to +0.45%, with or without the
trailing stop, all give +$4.42), so the result sits on a plateau, not a
spike. Looser settings trade far more and lose on every window checked:
a 10-minute / +0.20% confirmation loses $16.86 on the dev window, and
entering on the EMA state instead of the cross event loses $33.28. The
same bot makes no trade at all on the time-reversed or sign-flipped
dev window, i.e. it stays out of a falling market rather than fighting
it. Nothing here is fitted to a single bar: the entry needs both a
cross and a real move, and the exit is the trend turning, not a level.

Deterministic: no randomness, no wall clock, no environment reads, no
files. The only state is the closes seen, the two EMAs and the peak
value of the open position, so two runs on the same bars produce
byte-identical action logs.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"

# The two averages: 8 and 13 one-minute closes. Short enough to react
# inside a single strong hour, long enough that a one-minute spike in
# either one cannot flip the signal on its own.
FAST_SPAN = 8
SLOW_SPAN = 13

# Entry confirmation: the close must be this far above the close
# CONFIRM_BARS minutes ago (basis points).
CONFIRM_BARS = 15
CONFIRM_BPS = 45

# Exit: sell the whole position once its value has fallen this far
# (basis points) below the highest value it reached since entry.
TRAIL_BPS = 75

# Minimum hold: never exit on a cross-down within this many bars of
# entry. A cross-down that fast is one-minute noise, and the round trip
# already cost ~26 bps in fees, slippage and price impact, so an instant
# exit locks in a near-certain loss. The trailing stop above stays live
# during the hold, so a real drop still gets out immediately. On the dev
# window the one trade is held 46 bars, so the rule does not change it;
# on a synthetic whipsaw (a 2-bar dip 2 bars after entry that flips the
# gap without tripping the stop) the old bot sells at a $7.19 loss while
# this bot holds through and keeps the position.
MIN_HOLD_BARS = 10

BUY_SLIPPAGE_BPS = 200
SELL_SLIPPAGE_BPS = 10000


class MovingAverage:
    """An exponential moving average over integer closes.

    Seeded as the plain mean of its first span of closes, then each new
    close moves it 2 / (span + 1) of the way toward that close, exactly
    like the kit's ema-cross baseline.
    """

    def __init__(self, span):
        self.span = span
        self._warmup = []
        self.value = None

    def add(self, close):
        if self.value is not None:
            self.value += (2.0 / (self.span + 1)) * (close - self.value)
            return
        self._warmup.append(close)
        if len(self._warmup) == self.span:
            self.value = sum(self._warmup) / self.span


class Trend:
    """The fast-minus-slow gap, this bar and the bar before it."""

    def __init__(self):
        self.fast = MovingAverage(FAST_SPAN)
        self.slow = MovingAverage(SLOW_SPAN)
        self.gap = None        # fast - slow after the latest bar
        self.prev_gap = None   # fast - slow after the bar before that
        self.turned_down = False  # set on a cross down, held while slow stays above

    def add(self, close):
        self.fast.add(close)
        self.slow.add(close)
        if self.fast.value is None or self.slow.value is None:
            return
        self.prev_gap = self.gap
        self.gap = self.fast.value - self.slow.value
        if self.prev_gap is not None and self.prev_gap >= 0 and self.gap < 0:
            self.turned_down = True
        if self.gap >= 0:
            self.turned_down = False

    def crossed_up(self):
        """True on the bar the fast average first moves above the slow one."""
        return (self.gap is not None and self.prev_gap is not None
                and self.gap > 0 and self.prev_gap <= 0)


trend = Trend()
closes = []       # every close seen, in bar order
peak_value = 0    # highest value of the open position since entry
entry_seq = None  # batch seq of the bar the buy was decided on


def _sell_all(held):
    return [{"side": "sell", "symbol": SYMBOL, "qty": held.qty,
             "max_slippage_bps": SELL_SLIPPAGE_BPS}]


def _buy_all(state):
    amount = state.cash
    if amount < int(state.hello["fees"]["min_notional_quote_units"]):
        return []
    return [{"side": "buy", "symbol": SYMBOL,
             "notional_quote_units": amount,
             "max_slippage_bps": BUY_SLIPPAGE_BPS}]


def on_batch(state, batch):
    global peak_value, entry_seq
    seq = batch.get("seq")
    for bar in batch["bars"]:
        if bar["symbol"] != SYMBOL:
            continue
        close = int(bar["c"])
        closes.append(close)
        trend.add(close)
    if state.warming_up:
        return []
    held = state.positions.get(SYMBOL)
    close = state.close(SYMBOL)
    if close is None:
        return []
    if held is not None:
        value = state.value(SYMBOL, held.qty)
        if value > peak_value:
            peak_value = value
        bars_held = None if (seq is None or entry_seq is None) else seq - entry_seq
        if trend.turned_down and (bars_held is None or bars_held >= MIN_HOLD_BARS):
            return _sell_all(held)
        if peak_value and value * 10000 <= peak_value * (10000 - TRAIL_BPS):
            return _sell_all(held)
        return []
    peak_value = 0
    entry_seq = None
    if trend.crossed_up() and len(closes) > CONFIRM_BARS:
        then = closes[-1 - CONFIRM_BARS]
        if (close - then) * 10000 > then * CONFIRM_BPS:
            orders = _buy_all(state)
            if orders:
                entry_seq = seq
            return orders
    return []


makefun_bars.run(on_batch)
