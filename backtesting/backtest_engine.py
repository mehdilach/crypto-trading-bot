"""
Backtest des strategies du bot sur donnees historiques OHLCV.

Reutilise la meme interface Strategy (strategies/base.py) et le meme
RiskManager (garde-fous) que le bot live : on teste strategie + risque
ensemble, pas la strategie seule.

Simulation:
- capital initial fictif, taille d'ordre plafonnee (RiskManager.cap_order_size)
- frais 0.1% par ordre (standard Binance) + slippage simple par defaut 0.05%
- stop-loss intra-bougie : declenche si le LOW de la bougie passe sous le seuil
  (execution au prix seuil, conservateur)

Usage:
    python backtesting/backtest_engine.py --data backtesting/data/btc_usdt_5m.csv
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from risk_manager import RiskManager
from regime_filter import detect_regime
from strategies.base import Signal
from strategies.moving_average_crossover import MovingAverageCrossover
from strategies.rsi_mean_reversion import RsiMeanReversion
from trailing_risk_manager import TrailingStopRiskManager

COLONNES = ["ts", "open", "high", "low", "close", "volume"]


class BacktestEngine:
    def __init__(
        self,
        strategy,
        initial_capital=1000.0,
        max_order_size=50.0,
        fee_rate=0.001,
        slippage=0.0005,
        stop_loss_pct=None,
        window_size=100,
        risk_mode="fixed",
        trailing_pct=2.0,
        regime_filter=False,
        strategy_type="ma",
    ):
        self.strategy = strategy
        self.capital = initial_capital
        self.max_order_size = max_order_size
        self.fee_rate = fee_rate
        self.slippage = slippage
        self.window_size = window_size
        self.risk_mode = risk_mode
        self.trailing_pct = float(trailing_pct)
        if risk_mode == "trailing":
            self.risk = TrailingStopRiskManager(
                max_order_size=max_order_size,
                stop_loss_pct=stop_loss_pct,
                trailing_pct=trailing_pct,
            )
        else:
            self.risk = RiskManager(max_order_size=max_order_size, stop_loss_pct=stop_loss_pct)
        self.regime_filter = regime_filter
        self.strategy_type = strategy_type
        self._regimes_autorises = {"range"} if strategy_type == "rsi" else {"bull", "bear"}
        self._closes_hist: list = []
        self._regime_counts = {"bull": 0, "bear": 0, "range": 0, "chaos": 0}
        self._entree_autorisee = True

    def _prix_achat(self, close):
        return close * (1 + self.slippage)

    def _prix_vente(self, close):
        return close * (1 - self.slippage)

    def run(self, donnees: pd.DataFrame) -> dict:
        if list(donnees.columns) != COLONNES:
            raise ValueError(f"Colonnes attendues: {COLONNES}, recu: {list(donnees.columns)}")
        self.capital = float(self.capital)
        cash = self.capital
        units = 0.0
        entry_price = None
        entry_ts = None
        cout_achat = 0.0

        trades = []
        equity_curve = []
        peak_price = None

        for i in range(len(donnees)):
            bougie = donnees.iloc[i]
            ts = int(bougie["ts"])
            close = float(bougie["close"])
            low = float(bougie["low"])
            high = float(bougie["high"])

            if self.regime_filter:
                self._closes_hist.append(close)
                if len(self._closes_hist) > 210:
                    del self._closes_hist[:-210]
                regime = detect_regime(self._closes_hist)
                self._regime_counts[regime] += 1
                self._entree_autorisee = regime in self._regimes_autorises
                if i % 100 == 0:
                    print(f"  [regime] bougie {i} (ts={ts}) -> {regime}")

            seuil = None
            if units > 0:
                if self.risk_mode == "trailing":
                    peak_price = max(peak_price, high)
                    seuil = peak_price * (1 - self.trailing_pct / 100.0)
                elif entry_price is not None and self.risk.stop_loss_pct > 0:
                    seuil = entry_price * (1 - self.risk.stop_loss_pct / 100.0)

            if seuil is not None and low <= seuil:
                prix = seuil
                produit = units * prix
                frais = produit * self.fee_rate
                cash += produit - frais
                pnl = (produit - frais) - cout_achat
                trades.append({
                    "pnl": pnl,
                    "rendement": pnl / cout_achat if cout_achat else 0.0,
                    "duree_min": (ts - entry_ts) / 60000.0,
                    "motif": "stop-loss",
                })
                units = 0.0
                self.risk.clear_position()
                entry_price = None
                peak_price = None
                continue

            if i < self.window_size - 1:
                continue

            fenetre = donnees.iloc[i - self.window_size + 1 : i + 1].values.tolist()
            signal = self.strategy.evaluate(fenetre)

            if signal == Signal.BUY and units <= 0:
                bloquee = self.regime_filter and not self._entree_autorisee
                if not bloquee:
                    notional_cible = self.risk.cap_order_size(self.max_order_size)
                    notional = min(notional_cible, cash / (1 + self.fee_rate))
                    if notional <= 0:
                        continue
                    prix_achat = self._prix_achat(close)
                    units = notional / prix_achat
                    cout_achat = notional + notional * self.fee_rate
                    cash -= cout_achat
                    entry_price = close
                    entry_ts = ts
                    peak_price = close
                    self.risk.register_entry(entry_price)

            elif signal == Signal.SELL and units > 0:
                prix = self._prix_vente(close)
                produit = units * prix
                frais = produit * self.fee_rate
                cash += produit - frais
                pnl = (produit - frais) - cout_achat
                trades.append({
                    "pnl": pnl,
                    "rendement": pnl / cout_achat if cout_achat else 0.0,
                    "duree_min": (ts - entry_ts) / 60000.0,
                    "motif": "signal",
                })
                units = 0.0
                self.risk.clear_position()
                entry_price = None
                peak_price = None

            equity = cash + units * close
            equity_curve.append(equity)

        return self._metriques(donnees, trades, equity_curve)

    def _metriques(self, donnees, trades, equity_curve) -> dict:
        nb_trades = len(trades)
        total_pnl = sum(t["pnl"] for t in trades)
        pnl_moyen = total_pnl / nb_trades if nb_trades else 0.0
        gagnants = [t for t in trades if t["pnl"] > 0]
        win_rate = len(gagnants) / nb_trades if nb_trades else 0.0

        pic = equity_curve[0] if equity_curve else self.capital
        dd_max = 0.0
        for equity in equity_curve:
            pic = max(pic, equity)
            if pic > 0:
                dd_max = max(dd_max, (pic - equity) / pic * 100.0)

        rendements = [t["rendement"] for t in trades]
        if len(rendements) >= 2:
            moyenne = sum(rendements) / len(rendements)
            variance = sum((r - moyenne) ** 2 for r in rendements) / (len(rendements) - 1)
            ecart_type = variance ** 0.5
            sharpe = moyenne / ecart_type if ecart_type > 0 else 0.0
        else:
            sharpe = 0.0

        duree_moyenne = sum(t["duree_min"] for t in trades) / nb_trades if nb_trades else 0.0

        total_regime = sum(self._regime_counts.values())

        return {
            "nb_trades": nb_trades,
            "win_rate": win_rate,
            "total_pnl": total_pnl,
            "pnl_moyen": pnl_moyen,
            "max_drawdown_pct": dd_max,
            "sharpe": sharpe,
            "duree_moyenne_min": duree_moyenne,
            "capital_final": float(self.capital + total_pnl),
            "rendement_total_pct": total_pnl / self.capital * 100.0 if self.capital else 0.0,
            "dernier_motif": trades[-1]["motif"] if trades else None,
            "bougies": len(donnees),
            "regime_bull_pct": self._regime_counts["bull"] / total_regime if total_regime else 0.0,
            "regime_bear_pct": self._regime_counts["bear"] / total_regime if total_regime else 0.0,
            "regime_range_pct": self._regime_counts["range"] / total_regime if total_regime else 0.0,
            "regime_chaos_pct": self._regime_counts["chaos"] / total_regime if total_regime else 0.0,
        }

    def resumer(self, metriques: dict):
        print("=== Resultats du backtest ===")
        print(f"Nombre de trades            : {metriques['nb_trades']}")
        print(f"Win rate                    : {metriques['win_rate']:.1%}")
        print(f"P&L total                   : {metriques['total_pnl']:+.2f} USDT")
        print(f"P&L moyen par trade         : {metriques['pnl_moyen']:+.2f} USDT")
        print(f"Rendement total             : {metriques['rendement_total_pct']:+.2f}%")
        print(f"Capital final               : {metriques['capital_final']:.2f} USDT")
        print(f"Max drawdown                : {metriques['max_drawdown_pct']:.2f}%")
        print(f"Sharpe (simplifie)          : {metriques['sharpe']:.3f}")
        print(f"Duree moyenne de position   : {metriques['duree_moyenne_min']:.0f} min")
        print(f"Bougies analysees           : {metriques['bougies']}")
        if self.regime_filter:
            print(f"Regimes (bougies classees)  : bull {metriques['regime_bull_pct']:.1%} "
                  f"/ bear {metriques['regime_bear_pct']:.1%} / range {metriques['regime_range_pct']:.1%} "
                  f"/ chaos {metriques['regime_chaos_pct']:.1%}")


def charger_csv(chemin) -> pd.DataFrame:
    df = pd.read_csv(chemin)
    if list(df.columns) != COLONNES:
        raise ValueError(f"Colonnes attendues: {COLONNES}, recu: {list(df.columns)}")
    for col in COLONNES:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna().reset_index(drop=True)
    return df


WARMUP_BOUGIES = 210


def tronquer_dates(donnees: pd.DataFrame, debut: str | None, fin: str | None) -> pd.DataFrame:
    """Tronque un CSV OHLCV aux bornes de dates (UTC) avec warmup.

    Garde-fous : intervalle vide -> ValueError ; les 210 bougies precedant
    la borne de debut sont conservees (warmup MA(200) + filtre de regime)
    pour que la strategie soit operante des la premiere bougie du test.
    """
    dts = pd.to_datetime(donnees["ts"], unit="ms", utc=True)
    masque = pd.Series(True, index=donnees.index)
    if debut is not None:
        masque &= dts >= pd.Timestamp(debut, tz="UTC")
    if fin is not None:
        masque &= dts <= pd.Timestamp(fin, tz="UTC") + pd.Timedelta(hours=23, minutes=59)
    idx = donnees.index[masque]
    if len(idx) == 0:
        raise ValueError(f"Intervalle vide entre debut={debut} et fin={fin}")
    premiere = max(0, int(idx[0]) - WARMUP_BOUGIES)
    return donnees.loc[premiere : idx[-1]].reset_index(drop=True)


def main():
    parser = argparse.ArgumentParser(description="Backtest d'une strategie sur un CSV OHLCV")
    parser.add_argument("--data", default=str(Path(__file__).parent / "data" / "btc_usdt_5m.csv"))
    parser.add_argument("--capital", type=float, default=1000.0)
    parser.add_argument("--entry-size", type=float, default=50.0)
    parser.add_argument("--fee", type=float, default=0.001)
    parser.add_argument("--slippage", type=float, default=0.0005)
    parser.add_argument("--stop-loss-pct", type=float, default=None)
    parser.add_argument("--window", type=int, default=100)
    parser.add_argument("--fast", type=int, default=3, help="Periode MA rapide")
    parser.add_argument("--slow", type=int, default=7, help="Periode MA lente")
    parser.add_argument("--strategy", choices=["ma", "rsi"], default="ma",
                        help="Strategie: ma (croisement de MAs, defaut) ou rsi (mean-reversion)")
    parser.add_argument("--rsi-period", type=int, default=14, help="Periode RSI (strategie rsi)")
    parser.add_argument("--rsi-oversold", type=float, default=25.0, help="Seuil d'achat RSI (defaut 25)")
    parser.add_argument("--rsi-exit", type=float, default=55.0, help="Seuil de sortie RSI (defaut 55)")
    parser.add_argument("--risk-mode", choices=["fixed", "trailing"], default="fixed",
                        help="RiskManager: fixed (stop fixe, defaut) ou trailing (trailing-stop)")
    parser.add_argument("--trailing-pct", type=float, default=2.0,
                        help="Pourcentage de retrait depuis le plus haut (risk-mode trailing)")
    parser.add_argument("--regime-filter", action="store_true",
                        help="Filtre de regime: rsi -> entrees en range seul, ma -> en bull/bear seul")
    parser.add_argument("--start-date", default=None,
                        help="Borne de debut YYYY-MM-DD (UTC) — warmup de 210 bougies inclus automatiquement")
    parser.add_argument("--end-date", default=None,
                        help="Borne de fin YYYY-MM-DD (UTC), journee incluse")
    args = parser.parse_args()

    donnees = charger_csv(args.data)
    if args.start_date is not None or args.end_date is not None:
        donnees = tronquer_dates(donnees, args.start_date, args.end_date)
    print(f"Charge: {len(donnees)} bougies depuis {args.data}")
    if args.start_date is not None or args.end_date is not None:
        prem = pd.to_datetime(donnees.iloc[0]["ts"], unit="ms", utc=True).strftime("%Y-%m-%d %H:%M")
        dern = pd.to_datetime(donnees.iloc[-1]["ts"], unit="ms", utc=True).strftime("%Y-%m-%d %H:%M")
        print(f"Fenetre retenue (warmup inclus) : {prem} UTC -> {dern} UTC")

    if args.strategy == "rsi":
        strategy = RsiMeanReversion(
            period=args.rsi_period,
            oversold=args.rsi_oversold,
            exit_level=args.rsi_exit,
        )
        print(f"Strategie RSI({args.rsi_period}) oversold < {args.rsi_oversold:g}, sortie > {args.rsi_exit:g} "
              f"— frais {args.fee:.2%}, slippage {args.slippage:.2%}")
    else:
        strategy = MovingAverageCrossover(fast_period=args.fast, slow_period=args.slow)
        print(f"Strategie MA({args.fast})/MA({args.slow}) "
              f"— frais {args.fee:.2%}, slippage {args.slippage:.2%}")
    if args.risk_mode == "trailing":
        print(f"Mode risque: trailing-stop {args.trailing_pct:.2f}% depuis le plus haut")
    elif args.stop_loss_pct:
        print(f"Mode risque: stop-loss fixe {args.stop_loss_pct:.2f}% entrees")
    else:
        print("Mode risque: aucun stop-loss (position gardee jusqu'au signal)")
    if args.regime_filter:
        if args.strategy == "rsi":
            print("Filtre de regime ACTIF : entrees RSI uniquement en regime range (cash en bull/bear/chaos)")
        else:
            print("Filtre de regime ACTIF : entrees MA uniquement en regime bull/bear (cash en range/chaos)")

    engine = BacktestEngine(
        strategy=strategy,
        initial_capital=args.capital,
        max_order_size=args.entry_size,
        fee_rate=args.fee,
        slippage=args.slippage,
        stop_loss_pct=args.stop_loss_pct,
        window_size=args.window,
        risk_mode=args.risk_mode,
        trailing_pct=args.trailing_pct,
        regime_filter=args.regime_filter,
        strategy_type=args.strategy,
    )
    metriques = engine.run(donnees)
    engine.resumer(metriques)


if __name__ == "__main__":
    main()