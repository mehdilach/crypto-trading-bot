"""
Telecharge l'historique OHLCV de Binance (API publique, lecture seule, sans cles)
et le sauvegarde en CSV dans backtesting/data/ pour alimenter le backtest.

Usage:
    python backtesting/fetch_historical_data.py --days 180 --timeframe 5m
"""
import argparse
import time
from datetime import datetime, timezone
from pathlib import Path

import ccxt

DATA_DIR = Path(__file__).parent / "data"


def fetch_ohlcv(symbol: str, timeframe: str, days: int, exchange=None) -> list:
    exchange = exchange or ccxt.binance({"enableRateLimit": True})
    now = int(time.time() * 1000)
    since = now - days * 86400 * 1000

    toutes = []
    while since < now:
        lot = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=1000)
        if not lot:
            break
        toutes.extend(lot)
        since = lot[-1][0] + 1
        time.sleep(0.2)
    return toutes


def main():
    parser = argparse.ArgumentParser(description="Telecharge l'historique OHLCV Binance en CSV")
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--output", default=None, help="Chemin du CSV (defaut: backtesting/data/<symbole>_<timeframe>.csv)")
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    chemin = Path(args.output) if args.output else DATA_DIR / (args.symbol.replace("/", "_").lower() + "_" + args.timeframe + ".csv")

    print(f"Telechargement {args.symbol} {args.timeframe} sur {args.days} jours...")
    donnees = fetch_ohlcv(args.symbol, args.timeframe, args.days)

    if not donnees:
        print("Aucune donnee recue — verifie le symbole/timeframe.")
        raise SystemExit(1)

    with chemin.open("w", encoding="utf-8", newline="") as f:
        f.write("ts,open,high,low,close,volume\n")
        for ligne in donnees:
            f.write(",".join(str(v) for v in ligne[:6]) + "\n")

    debut = datetime.fromtimestamp(donnees[0][0] / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
    fin = datetime.fromtimestamp(donnees[-1][0] / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
    print(f"OK — {len(donnees)} bougies sauvegardees dans {chemin}")
    print(f"Couverture: {debut} UTC -> {fin} UTC")


if __name__ == "__main__":
    main()