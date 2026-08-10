"""
Point d'entrée du bot. Boucle : récupère les données -> évalue la stratégie
-> applique les garde-fous de risque -> passe l'ordre si signal -> attend -> répète.
"""
import logging
import time

import config
from exchange_client import build_exchange, get_last_price, place_market_order
from risk_manager import RiskManager
from state_manager import StateManager
from strategies.base import Signal
from strategies.moving_average_crossover import MovingAverageCrossover

LOOP_INTERVAL_SECONDS = 60
TIMEFRAME = "5m"
CANDLE_LIMIT = 100

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("logs/bot.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("crypto-bot.main")

state_manager = StateManager()


def run():
    config.validate()
    exchange = build_exchange()
    strategy = MovingAverageCrossover(fast_period=3, slow_period=7)
    risk = RiskManager()

    etat = state_manager.load_state()
    in_position = etat["in_position"]
    if in_position:
        risk.entry_price = etat["entry_price"]
        logger.warning(
            "Position existante restauree : entree a %s, symbole %s",
            etat["entry_price"], etat["symbol"] or config.SYMBOL,
        )
    logger.info("Bot démarré — symbole=%s, testnet=%s", config.SYMBOL, config.USE_TESTNET)

    while True:
        try:
            ohlcv = exchange.fetch_ohlcv(config.SYMBOL, timeframe=TIMEFRAME, limit=CANDLE_LIMIT)
            current_price = ohlcv[-1][4]  # close de la dernière bougie

            if in_position and risk.should_stop_loss(current_price):
                place_market_order(exchange, config.SYMBOL, Signal.SELL, config.MAX_ORDER_SIZE)
                state_manager.save_state(False, None, config.SYMBOL)
                risk.clear_position()
                in_position = False
                logger.info("Stop-loss execute — etat sauvegarde (position fermee).")
                time.sleep(LOOP_INTERVAL_SECONDS)
                continue

            signal = strategy.evaluate(ohlcv)

            if signal == Signal.BUY and not in_position:
                amount = risk.cap_order_size(config.MAX_ORDER_SIZE)
                place_market_order(exchange, config.SYMBOL, Signal.BUY, amount)
                risk.register_entry(current_price)
                in_position = True
                state_manager.save_state(True, current_price, config.SYMBOL)
                logger.info("Position ouverte — entree a %.2f, etat sauvegarde.", current_price)

            elif signal == Signal.SELL and in_position:
                place_market_order(exchange, config.SYMBOL, Signal.SELL, config.MAX_ORDER_SIZE)
                state_manager.save_state(False, None, config.SYMBOL)
                risk.clear_position()
                in_position = False
                logger.info("Position fermee — etat sauvegarde.")

            else:
                logger.info("Signal=%s, position=%s — rien à faire.", signal, in_position)

        except Exception:
            logger.exception("Erreur dans la boucle principale — le bot continue au prochain cycle.")

        time.sleep(LOOP_INTERVAL_SECONDS)


if __name__ == "__main__":
    run()
