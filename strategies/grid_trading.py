"""
Strategie Grid Trading : exploitation mecanique des regimes "range".

Mecanique (simplifiee pour le backtest) :
- Une grille de niveaux d'achat est construite entre un support et une
  resistance (bandes de Wick autour du min/max de la fenetre glissante),
  espacee d'un pas de grille (defaut 1.2%).
- En regime "range" : un niveau touche -> position achetee ; la hausse
  d'un cran fait vendre au niveau superieur (take-profit = +1 pas).
- Hors regime "range" (bull/bear/chaos) : plus aucune entree, les
  positions ouvertes sont liquidees au prix courant (la tendance casse
  la neutralite de la grille).

Garde-fous : pas_pct > 0 obligatoire, support <= 0 -> grille vide,
nombre de niveaux borne entre 2 et 50 (sinon grille inactive).
"""
import math

PAS_GRID_DEFAUT = 1.2
NB_NIVEAUX_MIN = 2
NB_NIVEAUX_MAX = 50


class GridStrategy:
    def __init__(self, pas_pct: float = PAS_GRID_DEFAUT):
        if pas_pct <= 0:
            raise ValueError(f"pas_pct doit etre > 0, recu: {pas_pct}")
        self.pas_pct = float(pas_pct)

    def pas_relatif(self) -> float:
        return 1.0 + self.pas_pct / 100.0

    def construire_niveaux(self, support: float, resistance: float) -> list:
        """Niveaux de la grille, ordre croissant. [] si geometrie invalide."""
        if support <= 0 or resistance <= support:
            return []
        rapport = resistance / support
        nb = int(round(math.log(rapport) / math.log(self.pas_relatif()))) + 1
        if nb < NB_NIVEAUX_MIN or nb > NB_NIVEAUX_MAX:
            return []
        return [support * (self.pas_relatif() ** k) for k in range(nb)]