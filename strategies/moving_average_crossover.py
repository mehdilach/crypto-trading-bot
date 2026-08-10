"""
Stratégie exemple, volontairement simple, pour valider que le pipeline complet
(données → décision → ordre → risque) fonctionne de bout en bout.
Ce n'est PAS une recommandation d'investissement — juste un point de départ à
remplacer par ta propre logique une fois le bot validé en testnet.
"""
import pandas as pd

from strategies.base import Strategy, Signal


class MovingAverageCrossover(Strategy):
    def __init__(self, fast_period: int = 9, slow_period: int = 21):
        self.fast_period = fast_period
        self.slow_period = slow_period

    def evaluate(self, ohlcv: list) -> str:
        if len(ohlcv) < self.slow_period + 1:
            return Signal.HOLD

        df = pd.DataFrame(ohlcv, columns=["ts", "open", "high", "low", "close", "volume"])
        fast_ma = df["close"].rolling(self.fast_period).mean()
        slow_ma = df["close"].rolling(self.slow_period).mean()

        prev_fast, prev_slow = fast_ma.iloc[-2], slow_ma.iloc[-2]
        curr_fast, curr_slow = fast_ma.iloc[-1], slow_ma.iloc[-1]

        crossed_up = prev_fast <= prev_slow and curr_fast > curr_slow
        crossed_down = prev_fast >= prev_slow and curr_fast < curr_slow

        if crossed_up:
            return Signal.BUY
        if crossed_down:
            return Signal.SELL
        return Signal.HOLD
