"""
Client d'échange — encapsule ccxt pour ne pas éparpiller la logique d'API dans tout le bot.
Basculer d'exchange plus tard (Kraken, Coinbase...) ne devrait toucher que ce fichier.
"""
import logging
import ccxt

import config

logger = logging.getLogger("crypto-bot.exchange")


def build_exchange():
    exchange = ccxt.binance({
        "apiKey": config.BINANCE_API_KEY,
        "secret": config.BINANCE_API_SECRET,
        "enableRateLimit": True,
    })
    if config.USE_TESTNET:
        exchange.set_sandbox_mode(True)
        logger.info("Mode TESTNET actif — aucun ordre réel ne sera passé.")
    else:
        logger.warning("Mode LIVE actif — les ordres engageront de l'argent réel.")
    return exchange


def get_last_price(exchange, symbol: str) -> float:
    ticker = exchange.fetch_ticker(symbol)
    return ticker["last"]


def get_balance(exchange, currency: str) -> float:
    balance = exchange.fetch_balance()
    return balance.get(currency, {}).get("free", 0.0)


def place_market_order(exchange, symbol: str, side: str, amount_quote: float):
    """
    Passe un ordre au marché. amount_quote est exprimé dans la devise de cotation
    (ex: USDT pour BTC/USDT) et converti en quantité de base au prix courant.
    """
    price = get_last_price(exchange, symbol)
    amount_base = amount_quote / price
    logger.info(
        "Ordre %s %s — montant ~%.2f (devise cotation) / %.6f (devise base) à ~%.2f",
        side.upper(), symbol, amount_quote, amount_base, price,
    )
    if side == "buy":
        return exchange.create_market_buy_order(symbol, amount_base)
    elif side == "sell":
        return exchange.create_market_sell_order(symbol, amount_base)
    else:
        raise ValueError(f"side invalide: {side} (attendu: 'buy' ou 'sell')")
