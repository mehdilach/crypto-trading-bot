"""
Strategie RSI mean-reversion (backtest).

Achat quand le RSI croise sous le seuil oversold (defaut 25),
vente quand il croise au-dessus du seuil de sortie (defaut 55,
PAS 70 : on vise un simple retour a la moyenne, pas l'exces inverse).
"""
from strategies.base import Strategy, Signal


def _rsi(closes: list, period: int) -> list:
    if len(closes) < period + 1:
        return []
    gains = []
    pertes = []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0.0))
        pertes.append(max(-delta, 0.0))

    ag = sum(gains[:period]) / period
    ap = sum(pertes[:period]) / period
    rsi = [0.0] * period
    if ap > 0:
        rsi.append(100.0 - 100.0 / (1.0 + ag / ap))
    else:
        rsi.append(100.0)

    for i in range(period, len(gains)):
        ag = (ag * (period - 1) + gains[i]) / period
        ap = (ap * (period - 1) + pertes[i]) / period
        if ap > 0:
            rsi.append(100.0 - 100.0 / (1.0 + ag / ap))
        else:
            rsi.append(100.0)
    return rsi


class RsiMeanReversion(Strategy):
    def __init__(self, period: int = 14, oversold: float = 25.0, exit_level: float = 55.0):
        self.period = period
        self.oversold = oversold
        self.exit_level = exit_level

    def evaluate(self, ohlcv: list) -> str:
        closes = [c[4] for c in ohlcv]
        rsi = _rsi(closes, self.period)
        if len(rsi) < 2:
            return Signal.HOLD

        prev, curr = rsi[-2], rsi[-1]
        if prev >= self.oversold and curr < self.oversold:
            return Signal.BUY
        if prev <= self.exit_level and curr > self.exit_level:
            return Signal.SELL
        return Signal.HOLD