# crypto-trading-bot

Bot d'exécution Python pour Binance, basé sur [ccxt](https://github.com/ccxt/ccxt).

⚠️ **Ceci n'est pas un conseil en investissement.** La stratégie fournie
(croisement de moyennes mobiles) est un exemple minimal pour valider le
pipeline technique — pas une recommandation de trading. Teste toujours
en testnet avant d'engager de l'argent réel, et ne risque jamais plus
que ce que tu peux perdre.

## Structure

```
crypto-trading-bot/
├── main.py                    # boucle principale
├── config.py                  # chargement de la config depuis .env
├── exchange_client.py         # wrapper ccxt (Binance)
├── risk_manager.py            # garde-fous : taille max, stop-loss
├── strategies/
│   ├── base.py                 # interface commune à toute stratégie
│   └── moving_average_crossover.py  # stratégie exemple
├── logs/                       # logs runtime (ignorés par git)
├── .env.example                # template de config
└── requirements.txt
```

## Installation

```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env         # puis édite .env avec tes vraies valeurs
```

## Configuration (.env)

| Variable            | Description                                              |
|----------------------|-----------------------------------------------------------|
| `BINANCE_API_KEY`    | Clé API Binance (ou testnet)                              |
| `BINANCE_API_SECRET` | Secret API associé                                        |
| `USE_TESTNET`        | `true` par défaut — reste sur testnet tant que non validé |
| `SYMBOL`              | Paire tradée, ex: `BTC/USDT`                               |
| `MAX_ORDER_SIZE`      | Montant max par ordre (devise de cotation)                 |
| `STOP_LOSS_PCT`       | % de perte déclenchant une sortie automatique              |

### Générer des clés testnet
1. Va sur https://testnet.binance.vision
2. Connecte-toi avec GitHub
3. Génère une clé API testnet (argent fictif, aucun risque réel)

## Lancer le bot

```bash
python main.py
```

Le bot tourne en boucle continue, log dans `logs/bot.log` et dans la console.
Arrête-le avec `Ctrl+C`.

## Avant de passer en argent réel

- [ ] Le bot a tourné plusieurs jours en testnet sans comportement inattendu
- [ ] Tu as relu et compris chaque ligne de `strategies/` — c'est TA logique de trading
- [ ] `MAX_ORDER_SIZE` est réglé à un montant que tu es prêt à perdre entièrement
- [ ] `STOP_LOSS_PCT` correspond à ta tolérance réelle au risque
- [ ] Tu as un moyen de surveiller le bot (logs, alertes) pendant qu'il tourne
- [ ] `USE_TESTNET=false` n'est changé qu'en toute connaissance de cause

## Étapes suivantes possibles
- Ajouter une notification Telegram/Discord à chaque ordre passé
- Ajouter un module de backtesting pour valider une stratégie sur données historiques
  avant de la lancer en conditions réelles
- Suivre performance/PnL dans une base (SQLite ou autre) plutôt que juste les logs
