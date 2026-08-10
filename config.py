"""
Configuration centralisée du bot.
Toutes les variables sensibles/ajustables passent par .env — jamais en dur dans le code.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")


def _get_bool(key: str, default: bool) -> bool:
    val = os.environ.get(key, str(default)).strip().lower()
    return val in ("1", "true", "yes", "on")


def _get_float(key: str, default: float) -> float:
    val = os.environ.get(key, "").strip()
    return float(val) if val else default


BINANCE_API_KEY = os.environ.get("BINANCE_API_KEY", "").strip()
BINANCE_API_SECRET = os.environ.get("BINANCE_API_SECRET", "").strip()
USE_TESTNET = _get_bool("USE_TESTNET", True)
SYMBOL = os.environ.get("SYMBOL", "BTC/USDT").strip()
MAX_ORDER_SIZE = _get_float("MAX_ORDER_SIZE", 50.0)
STOP_LOSS_PCT = _get_float("STOP_LOSS_PCT", 2.0)


def validate():
    """Appelé au démarrage — échoue vite et clairement plutôt que planter plus loin."""
    errors = []
    if not BINANCE_API_KEY:
        errors.append("BINANCE_API_KEY manquante dans .env")
    if not BINANCE_API_SECRET:
        errors.append("BINANCE_API_SECRET manquante dans .env")
    if MAX_ORDER_SIZE <= 0:
        errors.append("MAX_ORDER_SIZE doit être > 0")
    if errors:
        raise RuntimeError("Configuration invalide:\n- " + "\n- ".join(errors))
