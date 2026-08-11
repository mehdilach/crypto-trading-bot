"""
Filtre de regime de marche pour le backtesting.

detect_regime(closes, window=200) -> "bull" | "bear" | "range" | "chaos"

Architecture (ordre strict) :

  ÉTAPE 0 - Garde-fou data :
    historique insuffisant (len(closes) < window + 10) -> "chaos"

  ÉTAPE 1 - Chaos (priorite absolue) :
    ATR(14) normalise = ATR14 / close[-1] (proxie closes seules :
    moyenne des |close[i] - close[i-1]| sur les 14 dernieres bougies).
    ATR normalise > SEUIL_ATR_CHAOS -> "chaos"
    (bougies geantes, news, volatilite explosive -> ne rien trader)

  ÉTAPE 2 - Pente de MA(window) :
    slope = (MA[-1] - MA[-N]) / MA[-N], N = 10 bougies.
    slope > +SEUIL_SLOPE  -> candidat "bull"
    slope < -SEUIL_SLOPE  -> candidat "bear"
    sinon                 -> candidat "range"

  ÉTAPE 3 - Confirmation par ATR normalise :
    candidat bull/bear ET ATR > SEUIL_ATR_TREND  -> confirme bull/bear
    candidat bull/bear ET ATR < SEUIL_ATR_RANGE  -> reclasse "range"
    cas mixtes restants                          -> "range" par defaut

Seuils calibres sur SOL/USDT 1h (2 ans, backtesting/data/sol_usdt_1h.csv) :
  ~33% bull / ~31% bear / ~29% range / ~7% chaos — voir
  backtesting/test_regime.py (--data pour changer d'actif).

Testable isolement : python backtesting/regime_filter.py
"""

import logging
from typing import List

logger = logging.getLogger("crypto-bot.regime")

N_PENTE = 10
SEUIL_SLOPE = 0.0010
SEUIL_ATR_CHAOS = 0.0100
SEUIL_ATR_TREND = 0.0030
SEUIL_ATR_RANGE = 0.0025
PERIODE_ATR = 14


def _moyenne_mobile(closes: List[float], periode: int) -> List[float]:
    """MA simple glissante, alignee sur la fin de chaque fenetre.

    ma[k] = moyenne de closes[k-periode+1..k] ;
    len(ma) = len(closes) - periode + 1.
    """
    ma: List[float] = []
    somme = 0.0
    for i, c in enumerate(closes):
        somme += c
        if i >= periode:
            somme -= closes[i - periode]
        if i >= periode - 1:
            ma.append(somme / periode)
    return ma


def _atr_normalise(closes: List[float], periode: int = PERIODE_ATR) -> float:
    """Proxie ATR(periode) normalise par le dernier close.

    Calculable en closes seules (signature publique imposee) :
    moyenne des |close[i] - close[i-1]| sur les `periode` dernieres
    variations, divisee par close[-1].
    Anti-bug : si close[-1] == 0 -> retourne 0.0.
    """
    if len(closes) < periode + 1:
        return 0.0
    dernier = closes[-1]
    if dernier <= 0:
        return 0.0
    variations = [
        abs(closes[i] - closes[i - 1])
        for i in range(len(closes) - periode, len(closes))
    ]
    return sum(variations) / periode / dernier


def detect_regime(closes: List[float], window: int = 200) -> str:
    """Classe le regime de marche courant : "bull" | "bear" | "range" | "chaos".

    Args:
        closes: cours de cloture, du plus ancien au plus recent.
        window: periode de la moyenne mobile (defaut 200).

    Returns:
        Etat de regime (historique insuffisant -> "chaos").
    """
    # ÉTAPE 0 - Garde-fou data : pas assez d'historique pour calculer quoi
    # que ce soit de fiable. Anti-IndexError (len(closes) < window + 10
    # rendrait le slice ma[-N_PENTE] impossible).
    if len(closes) < window + N_PENTE:
        logger.debug("regime: historique insuffisant (%d < %d) -> chaos",
                     len(closes), window + N_PENTE)
        return "chaos"

    # ÉTAPE 1 - Chaos : volatilite explosive -> aucune strategie ne trade.
    atr_norm = _atr_normalise(closes)
    if atr_norm > SEUIL_ATR_CHAOS:
        logger.debug("regime: chaos (atr_norm=%.5f > %.5f)", atr_norm, SEUIL_ATR_CHAOS)
        return "chaos"

    # ÉTAPE 2 - Pente de MA(window) sur N_PENTE bougies. Anti-bug : si la MA
    # passee est <= 0 (donnees aberrantes), pente neutralisee a 0.0.
    ma = _moyenne_mobile(closes, window)
    ma_courant = ma[-1]
    ma_passe = ma[-N_PENTE]
    if ma_passe <= 0:
        pente = 0.0
    else:
        pente = (ma_courant - ma_passe) / ma_passe

    if pente > SEUIL_SLOPE:
        candidat = "bull"
    elif pente < -SEUIL_SLOPE:
        candidat = "bear"
    else:
        candidat = "range"

    # ÉTAPE 3 - Confirmation par ATR normalise (CAS MIXTES -> "range").
    if candidat in ("bull", "bear"):
        if atr_norm > SEUIL_ATR_TREND:
            logger.debug("regime: %s confirme (slope=%+.5f, atr_norm=%.5f)",
                         candidat, pente, atr_norm)
            return candidat
        if atr_norm < SEUIL_ATR_RANGE:
            logger.debug("regime: candidat %s reclass en range (atr_norm=%.5f < %.5f)",
                         candidat, atr_norm, SEUIL_ATR_RANGE)
            return "range"
        logger.debug("regime: cas mixte (slope=%+.5f, atr_norm=%.5f) -> range",
                     pente, atr_norm)
        return "range"

    logger.debug("regime: range confirme (slope=%+.5f, atr_norm=%.5f)", pente, atr_norm)
    return "range"


if __name__ == "__main__":
    bull = [100.0 * (1.02 ** i) for i in range(300)]
    bear = [100.0 * (0.98 ** i) for i in range(300)]
    print("trend haussier +2%/bougie ->", detect_regime(bull))
    print("trend baissier -2%/bougie ->", detect_regime(bear))
    print("serie plate              ->", detect_regime([100.0] * 300))
    print("historique insuffisant   ->", detect_regime([1.0] * 100))
    print("choc volatil             ->", detect_regime([100.0] * 209 + [103.0] * 10))