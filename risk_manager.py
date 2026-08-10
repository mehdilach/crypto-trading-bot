"""
Garde-fous exécutés AVANT tout ordre. Le but : qu'un bug de stratégie ne puisse
jamais engager plus que ce qui est explicitement autorisé en config.
"""
import logging

import config

logger = logging.getLogger("crypto-bot.risk")


class RiskManager:
    def __init__(self, max_order_size: float = None, stop_loss_pct: float = None):
        self.max_order_size = max_order_size or config.MAX_ORDER_SIZE
        self.stop_loss_pct = stop_loss_pct or config.STOP_LOSS_PCT
        self.entry_price = None

    def cap_order_size(self, requested_amount: float) -> float:
        if requested_amount > self.max_order_size:
            logger.warning(
                "Ordre demandé (%.2f) > plafond autorisé (%.2f) — plafonné.",
                requested_amount, self.max_order_size,
            )
            return self.max_order_size
        return requested_amount

    def register_entry(self, price: float):
        self.entry_price = price

    def should_stop_loss(self, current_price: float) -> bool:
        if self.entry_price is None:
            return False
        drop_pct = (self.entry_price - current_price) / self.entry_price * 100
        if drop_pct >= self.stop_loss_pct:
            logger.warning(
                "Stop-loss déclenché : entrée %.2f, prix actuel %.2f (-%.2f%%)",
                self.entry_price, current_price, drop_pct,
            )
            return True
        return False

    def clear_position(self):
        self.entry_price = None
