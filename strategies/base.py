"""
Interface commune à toutes les stratégies.
Chaque stratégie ne fait qu'une chose : regarder des données et dire quoi faire.
Elle ne place jamais d'ordre elle-même (ça reste la responsabilité de l'executor).
"""
from abc import ABC, abstractmethod


class Signal:
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class Strategy(ABC):
    @abstractmethod
    def evaluate(self, ohlcv: list) -> str:
        """
        Reçoit une liste de bougies OHLCV récentes (format ccxt :
        [timestamp, open, high, low, close, volume]) et retourne
        Signal.BUY, Signal.SELL ou Signal.HOLD.
        """
        raise NotImplementedError
