"""
Script de validation de la brique 1 (regime_filter.py).

Charge le CSV 1h reel (backtesting/data/btc_usdt_1h.csv), classe le
regime de chaque bougie avec detect_regime(), affiche le regime
toutes les 50 bougies puis la distribution globale
(% bull / bear / range / chaos).

Critere de calibrage (spec brique 1) :
    range >= 10% ET bull+bear >= 20%
Sinon -> "SEUILS MAL CALIBRES" (il faut ajuster regime_filter.py).

Aucun crash tolere : si une exception survient, le script affiche
l'erreur avec la bougie fautive et sort en code 1.
"""
import argparse
import csv
import datetime
import sys
from collections import Counter
from pathlib import Path

from regime_filter import detect_regime

CHEMIN_DEFAUT = Path(__file__).resolve().parent / "data" / "btc_usdt_1h.csv"
WINDOW = 200          # periode MA du filtre
BUFFER = WINDOW + 10  # fenetre glissante exacte de detect_regime


def main() -> int:
    parser = argparse.ArgumentParser(description="Valide la distribution des regimes sur un CSV OHLCV")
    parser.add_argument("--data", default=str(CHEMIN_DEFAUT),
                        help="Chemin du CSV 1h (ex: backtesting/data/sol_usdt_1h.csv)")
    args = parser.parse_args()
    chemin_csv = Path(args.data)

    if not chemin_csv.exists():
        print(f"[ERREUR] CSV introuvable : {chemin_csv}")
        return 1

    closes: list = []
    timestamps: list = []
    with open(chemin_csv, newline="") as f:
        for ligne in csv.DictReader(f):
            closes.append(float(ligne["close"]))
            timestamps.append(int(ligne["ts"]))

    nb_bougies = len(closes)
    print(f"CSV charge : {nb_bougies} bougies depuis {chemin_csv.name}")
    print(f"Fenetre glissante : {BUFFER} bougies (MA {WINDOW} + pente 10)\n")

    distribution: Counter = Counter()
    try:
        for j in range(BUFFER - 1, nb_bougies):
            fenetre = closes[j - BUFFER + 1 : j + 1]
            regime = detect_regime(fenetre)
            distribution[regime] += 1
            if j % 50 == 0:
                ts_h = datetime.datetime.fromtimestamp(
                    timestamps[j] / 1000.0, tz=datetime.timezone.utc
                ).strftime("%Y-%m-%d %H:%M")
                print(f"  bougie {j:6d} ({ts_h} UTC) -> {regime}")
    except Exception as exc:  # anti-crash : on degrade proprement
        print(f"\n[CRASH] exception a la bougie {j}: {type(exc).__name__}: {exc}")
        return 1

    total = sum(distribution.values())
    print("\n=== DISTRIBUTION GLOBALE (bougies classees)")
    for regime in ("bull", "bear", "range", "chaos"):
        pct = distribution[regime] / total * 100.0 if total else 0.0
        print(f"  {regime:6s} : {distribution[regime]:6d}  ({pct:5.1f}%)")

    pct_range = distribution["range"] / total * 100.0
    pct_trend = (distribution["bull"] + distribution["bear"]) / total * 100.0
    print(f"\n  bougies classees : {total}  (sans crash)")

    if pct_range >= 10.0 and pct_trend >= 20.0:
        print("VALIDATION BRIQUE 1 : OK (range >= 10% et bull+bear >= 20%)")
        return 0
    print("VALIDATION BRIQUE 1 : ECHEC -> SEUILS MAL CALIBRES")
    return 2


if __name__ == "__main__":
    sys.exit(main())