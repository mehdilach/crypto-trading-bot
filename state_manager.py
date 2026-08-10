"""
Persistance d'etat du bot (position ouverte, prix d'entree) pour survivre
aux redemarrages et redeploiements.

Mode Turso  : si TURSO_DATABASE_URL est defini (avec TURSO_AUTH_TOKEN),
              l'etat vit dans une base libSQL distante — survit aux
              redeploiements Render (plan Free = filesystem ephemere).
Mode fichier: sinon, repli local atomique sur state.json (dev sans reseau).

Interface stable: save_state(in_position, entry_price, symbol) /
load_state() -> dict. Le reste du bot ne change pas.
"""
import json
import logging
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("crypto-bot.state")

STATE_FILE = Path(__file__).parent / "state.json"
DEFAUT = {"in_position": False, "entry_price": None, "symbol": None}

TURSO_URL = os.environ.get("TURSO_DATABASE_URL", "").strip()
TURSO_TOKEN = os.environ.get("TURSO_AUTH_TOKEN", "").strip()
MODE_TURSO = bool(TURSO_URL)

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS bot_state (
    id TEXT PRIMARY KEY,
    in_position INTEGER NOT NULL DEFAULT 0,
    entry_price REAL,
    symbol TEXT,
    updated_at TEXT NOT NULL
)
"""
_UPSERT_SQL = """
INSERT INTO bot_state (id, in_position, entry_price, symbol, updated_at)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT(id) DO UPDATE SET
    in_position = excluded.in_position,
    entry_price = excluded.entry_price,
    symbol = excluded.symbol,
    updated_at = excluded.updated_at
"""
_SELECT_SQL = (
    "SELECT in_position, entry_price, symbol, updated_at "
    "FROM bot_state WHERE id = ?"
)
_LIGNE_CURRENT = "current"


def _normaliser_ligne(ligne):
    """Normalise une ligne Turso en dict — la lib renvoie des tuples nus."""
    if ligne is None:
        return None
    if isinstance(ligne, dict):
        valeurs = [ligne.get(c) for c in ("in_position", "entry_price", "symbol", "updated_at")]
    elif isinstance(ligne, (tuple, list)):
        valeurs = list(ligne)
    else:
        valeurs = [ligne[c] for c in ("in_position", "entry_price", "symbol", "updated_at")]
    in_position, entry_price, symbol, _ = (valeurs + [None] * 4)[:4]
    return {
        "in_position": bool(int(in_position)) if in_position is not None else False,
        "entry_price": float(entry_price) if entry_price is not None else None,
        "symbol": symbol,
    }


class StateManager:
    def __init__(self, chemin=STATE_FILE):
        self.chemin = Path(chemin)
        self._conn = None
        if MODE_TURSO:
            logger.info("Mode stockage: TURSO distant (%s)", TURSO_URL.split("?")[0])
        else:
            logger.info("Mode stockage: fichier local (%s)", self.chemin)

    def save_state(self, in_position, entry_price, symbol):
        etat = {
            "in_position": bool(in_position),
            "entry_price": entry_price,
            "symbol": symbol,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if MODE_TURSO:
            self._save_turso(etat)
        else:
            self._save_fichier(etat)

    def load_state(self):
        if MODE_TURSO:
            return self._load_turso()
        return self._load_fichier()

    def _connecter_turso(self, tentative=0):
        if self._conn is not None:
            return True
        try:
            from turso_serverless import connect as turso_connect
            conn = turso_connect(TURSO_URL, auth_token=TURSO_TOKEN or None)
            conn.execute(_SCHEMA_SQL)
            conn.commit()
            self._conn = conn
            return True
        except Exception as e:
            self._conn = None
            if tentative < 2:
                time.sleep(1.0)
                return self._connecter_turso(tentative + 1)
            logger.warning(
                "Connexion Turso impossible (%s: %s) — etat par defaut sûr sans base.",
                type(e).__name__, e,
            )
            return False

    def _save_turso(self, etat):
        if not self._connecter_turso():
            logger.error("Etat NON sauvegarde (Turso indisponible): in_position=%s", etat["in_position"])
            return
        params = (
            _LIGNE_CURRENT,
            1 if etat["in_position"] else 0,
            etat["entry_price"],
            etat["symbol"],
            etat["updated_at"],
        )
        try:
            self._conn.execute(_UPSERT_SQL, params)
            self._conn.commit()
        except Exception as e:
            self._conn = None
            logger.warning("Ecriture Turso echouee (%s: %s) — reconnexion.", type(e).__name__, e)
            if self._connecter_turso():
                try:
                    self._conn.execute(_UPSERT_SQL, params)
                    self._conn.commit()
                except Exception as e2:
                    self._conn = None
                    logger.error(
                        "Ecriture Turso echouee apres reconnexion (%s: %s) — etat non persiste.",
                        type(e2).__name__, e2,
                    )

    def _load_turso(self):
        if not self._connecter_turso():
            return dict(DEFAUT)
        try:
            ligne = _normaliser_ligne(self._conn.execute(_SELECT_SQL, (_LIGNE_CURRENT,)).fetchone())
            if ligne is None:
                return dict(DEFAUT)
            return ligne
        except Exception as e:
            self._conn = None
            logger.warning(
                "Lecture Turso echouee (%s: %s) — tentative de reconnexion.",
                type(e).__name__, e,
            )
            if self._connecter_turso():
                try:
                    ligne = _normaliser_ligne(
                        self._conn.execute(_SELECT_SQL, (_LIGNE_CURRENT,)).fetchone()
                    )
                    if ligne is not None:
                        return ligne
                except Exception as e2:
                    self._conn = None
                    logger.warning(
                        "Lecture Turso echouee apres reconnexion (%s: %s) — etat par defaut.",
                        type(e2).__name__, e2,
                    )
            return dict(DEFAUT)

    def _save_fichier(self, etat):
        dossier = self.chemin.parent
        tmp = None
        try:
            if not dossier.exists():
                dossier.mkdir(parents=True, exist_ok=True)
            tmp = tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=str(dossier),
                prefix="state.",
                suffix=".tmp",
                delete=False,
            )
            json.dump(etat, tmp, ensure_ascii=False, indent=2)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp.close()
            os.replace(tmp.name, self.chemin)
        except Exception as e:
            if tmp is not None and not tmp.closed:
                tmp.close()
            try:
                if tmp is not None:
                    os.unlink(tmp.name)
            except OSError:
                pass
            logger.warning("Echec d'ecriture de state.json: %s: %s", type(e).__name__, e)

    def _load_fichier(self):
        if not self.chemin.exists():
            return dict(DEFAUT)
        try:
            with self.chemin.open(encoding="utf-8") as f:
                data = json.load(f)
            etat = dict(DEFAUT)
            for cle in ("in_position", "entry_price", "symbol"):
                etat[cle] = data.get(cle)
            etat["in_position"] = bool(etat["in_position"])
            return etat
        except Exception as e:
            logger.warning(
                "state.json illisible ou corrompu (%s: %s) — etat par defaut: aucune position.",
                type(e).__name__, e,
            )
            return dict(DEFAUT)