"""
Point d'entrée du bot — déploiement de la stratégie GRID sur Binance Testnet.

Boucle : récupère l'historique 1h SOL/USDT -> maintient 210 closes pour
detect_regime -> en régime "range", active la grille (achat sur niveau
touché, take-profit au niveau supérieur = +1 pas) ; hors range, GEL des
nouvelles entrées (les take-profit des positions existantes restent
actifs). Paramètres backtestés et WFO-validés : pas de grille 2.5%.

Sécurité : USE_TESTNET doit être strictement True dans config — sinon le
bot refuse de démarrer. Aucun ordre réel ne peut partir.
"""
import logging
import time

import config
from backtesting.regime_filter import detect_regime
from exchange_client import build_exchange, place_market_order
from state_manager import StateManager
from strategies.grid_trading import GridStrategy

LOOP_INTERVAL_SECONDS = 60
TIMEFRAME = "1h"
HISTORIQUE_CLOSES = 210     # closes alimentant detect_regime (comme le backtest)
HISTORIQUE_BORNES = 2160    # 90 jours de bougies 1h pour les bornes de la grille
PAS_FETCH = 1000            # fetch_ohlcv Binance : 1000 lignes max par appel
SLEEP_FETCH = 0.3           # politesse rate-limit entre appels paginés
GRID_STEP_PCT = 2.5         # Var C WFO-validée
WARMUP_MIN_BOUGIES = 210    # le filtre est défensif en dessous (chaos -> gel)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("logs/bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("crypto-bot.main")

state_manager = StateManager()


def _duree_ms(timeframe: str) -> int:
    """Duree d'une bougie en ms depuis son code ccxt (1m/5m/1h/1d...)."""
    nb = int(timeframe[:-1])
    unite = timeframe[-1]
    return nb * {"m": 60_000, "h": 3_600_000, "d": 86_400_000}[unite]


def _fetch_historique(exchange, symbol: str, timeframe: str, nb_bougies: int) -> list:
    """Historique ordonné (ancien -> récent) de nb_bougies bougies fermées.

    Pagine vers le passé via since (compatible avec toutes les versions de
    ccxt), déduplique les chevauchements d'une tranche à l'autre. Chaque
    appel est protégé : en cas d'erreur réseau on retente après SLEEP_FETCH.
    """
    limite = min(PAS_FETCH, max(nb_bougies, 1))
    donnees = []
    since_ms = None
    while len(donnees) < nb_bougies:
        try:
            tranche = exchange.fetch_ohlcv(
                symbol, timeframe=timeframe, limit=limite, since=since_ms,
            )
        except Exception as e:
            logger.warning(
                "fetch_ohlcv échoué (%s: %s) — nouvelle tentative dans %.1fs.",
                type(e).__name__, e, SLEEP_FETCH,
            )
            time.sleep(SLEEP_FETCH)
            continue
        if not tranche:
            break
        connus = {b[0] for b in donnees}
        nouveaux = [b for b in tranche if b[0] not in connus]
        if not nouveaux:
            break
        donnees[0:0] = nouveaux
        since_ms = tranche[0][0] - _duree_ms(timeframe) * limite
        time.sleep(SLEEP_FETCH)
        if len(tranche) < limite:
            break
    return donnees


def _bougies_fermees(historique: list, now_ms: int) -> list:
    """Ne conserve que les bougies 1h terminées (ts <= now - 1h)."""
    limite = now_ms - 3600 * 1000
    return [b for b in historique if b[0] <= limite]


def run():
    if not config.USE_TESTNET:
        logger.error("REFUS DE DEMARRER : USE_TESTNET=False — aucun ordre réel ne doit partir.")
        raise SystemExit("USE_TESTNET doit être True (deploiement Testnet uniquement).")

    config.validate()
    exchange = build_exchange()
    grid = GridStrategy(pas_pct=GRID_STEP_PCT)

    slots = {}
    for s in state_manager.load_slots():
        slots[float(s["niveau"])] = {"units": float(s["units"]), "tp": float(s["tp"]),
                                     "ts": int(s["ts"])}
    if slots:
        logger.info("Grille restaurée : %d slot(s) en mémoire (%s).", len(slots), config.SYMBOL)

    regime_actuel = None
    dernier_ts = None
    niveaux = []

    logger.info("Bot GRID démarré — symbole=%s, timeframe=%s, pas=%s%%, testnet=%s",
                config.SYMBOL, TIMEFRAME, GRID_STEP_PCT, config.USE_TESTNET)

    while True:
        try:
            historique = _fetch_historique(exchange, config.SYMBOL, TIMEFRAME, HISTORIQUE_BORNES)
            if not historique:
                logger.warning("Historique vide — nouvelle tentative au prochain cycle.")
                time.sleep(LOOP_INTERVAL_SECONDS)
                continue

            now_ms = int(time.time() * 1000)
            fermees = _bougies_fermees(historique, now_ms)
            if len(fermees) < 2:
                time.sleep(LOOP_INTERVAL_SECONDS)
                continue

            derniere = fermees[-1]
            ts = derniere[0]
            current_price = float(derniere[4])
            low = float(derniere[3])
            high = float(derniere[2])

            if ts != dernier_ts:
                dernier_ts = ts
                closes = [float(b[4]) for b in fermees[-HISTORIQUE_CLOSES:]]
                regime = detect_regime(closes)
                if regime != regime_actuel:
                    if regime_actuel is not None:
                        logger.info("Régime passé de %s à %s.", regime_actuel, regime)
                    else:
                        logger.info("Régime initial détecté : %s.", regime)
                    if regime != "range":
                        logger.info("Gel des achats (hors range) — les take-profit restent actifs.")
                    else:
                        logger.info("Régime range — grille réactivée.")
                    regime_actuel = regime

                if len(closes) < WARMUP_MIN_BOUGIES:
                    logger.info("Warmup: %d/%d closes — filtre défensif (chaos) -> gel.",
                                len(closes), WARMUP_MIN_BOUGIES)
                    time.sleep(LOOP_INTERVAL_SECONDS)
                    continue

                if regime == "range":
                    lows = [float(b[3]) for b in fermees[-HISTORIQUE_BORNES:]]
                    highs = [float(b[2]) for b in fermees[-HISTORIQUE_BORNES:]]
                    niveaux = grid.construire_niveaux(0.85 * min(lows), 1.15 * max(highs))

                for niveau in list(slots):
                    slot = slots[niveau]
                    if high >= slot["tp"]:
                        try:
                            place_market_order(exchange, config.SYMBOL, "sell",
                                               slot["units"] * current_price)
                        except Exception as e:
                            logger.error("Vente TP impossible (%s: %s) — slot conservé.",
                                         type(e).__name__, e)
                            continue
                        del slots[niveau]
                        state_manager.save_slots(
                            [{"niveau": k, "units": v["units"], "tp": v["tp"], "ts": v["ts"]}
                             for k, v in slots.items()]
                        )
                        logger.info("Take Profit atteint : niveau %.2f (TP %.2f) — vendu à ~%.2f.",
                                    niveau, slot["tp"], current_price)

                if regime == "range" and niveaux:
                    notional_cellule = config.MAX_ORDER_SIZE / len(niveaux)
                    for niveau in niveaux:
                        if niveau in slots or low > niveau:
                            continue
                        try:
                            place_market_order(exchange, config.SYMBOL, "buy", notional_cellule)
                        except Exception as e:
                            logger.error("Achat impossible (%s: %s) — niveau %.2f ignoré.",
                                         type(e).__name__, e, niveau)
                            continue
                        slots[niveau] = {
                            "units": notional_cellule / max(current_price, 1e-8),
                            "tp": niveau * grid.pas_relatif(),
                            "ts": ts,
                        }
                        state_manager.save_slots(
                            [{"niveau": k, "units": v["units"], "tp": v["tp"], "ts": v["ts"]}
                             for k, v in slots.items()]
                        )
                        logger.info("Niveau de grille touché : achat %.2f USDT à ~%.2f "
                                    "(TP %.2f) — slot ouvert.", notional_cellule, niveau,
                                    niveau * grid.pas_relatif())

                logger.info("Bougie %s: régime=%s, grille=%d niveaux, %d slot(s) ouverts, "
                            "prix=%.2f.", ts, regime_actuel, len(niveaux), len(slots),
                            current_price)

        except Exception:
            logger.exception("Erreur dans la boucle principale — le bot continue au prochain cycle.")

        time.sleep(LOOP_INTERVAL_SECONDS)


if __name__ == "__main__":
    run()