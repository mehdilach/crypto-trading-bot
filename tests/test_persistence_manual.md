# Test manuel de persistance d'état (state_manager.py)

Objectif : vérifier qu'une position ouverte survit à un redémarrage brutal du
process (crash, `taskkill`, Ctrl+C, redémarrage Windows), et que le stop-loss
fonctionne sur la position restaurée.

Prérequis : `.env` rempli (testnet), venv actif.

## Étape 1 — Lancer le bot et attendre un BUY

```
cd C:\Users\lmehd\Desktop\crypto-trading-bot-v2
.\venv\Scripts\python.exe main.py
```

Attendre dans `logs/bot.log` la ligne :

```
Ordre BUY BTC/USDT — montant ~50.00 ... à ~XXXXX.XX
Position ouverte — entrée à XXXXX.XX, état sauvegardé.
```

Vérifier que le fichier `state.json` existe à la racine du projet et contient :

```json
{
  "in_position": true,
  "entry_price": <prix>,
  "symbol": "BTC/USDT"
}
```

## Étape 2 — Tuer le process brutalement

Dès que le BUY est passé, tuer sans ménagement (dans une autre console) :

```
taskkill /F /IM python.exe
```

ou Ctrl+C dans la console du bot. Ne pas laisser le bot se fermer proprement
ni passer un SELL : on veut simuler un crash en pleine position.

## Étape 3 — Relancer et vérifier la restauration

Relancer le bot :

```
.\venv\Scripts\python.exe main.py
```

Vérifier dans `logs/bot.log` la ligne d'avertissement immédiate (au démarrage) :

```
[WARNING] crypto-bot.main: Position existante restaurée depuis state.json :
entrée à <le prix du BUY>, symbole BTC/USDT
```

Ce prix d'entrée doit être **identique** à celui du BUY de l'étape 1 (pas celui
d'un nouveau signal). Le bot doit ensuite loguer `Signal=hold, position=True`
(des cycles, pas de re-buy par-dessus la position).

## Étape 4 — Vérifier le stop-loss sur la position restaurée

Avec un prix d'entrée de référence `P` (lu dans state.json), le stop-loss se
déclenche si le prix courant chute de `STOP_LOSS_PCT` (2.0 dans le .env) :

- si le marché chute de >= 2 % par rapport à l'entrée restaurée, attendre la
  ligne :

```
[WARNING] crypto-bot.risk: Stop-loss déclenché : entrée P, prix actuel X (-X.XX%)
Ordre SELL BTC/USDT — montant ~50.00 ...
Stop-loss exécuté — état sauvegardé (position fermée).
```

- sinon (marché stable/hausse), le signal SELL (crossover) finira par
  déclencher la sortie avec `Position fermée — état sauvegardé.`

Après fermeture, vérifier que `state.json` contient `"in_position": false` et
`"entry_price": null`.

## Cas dégradés à vérifier (facultatif)

1. Supprimer `state.json` puis relancer : aucun warning, le bot part
   `in_position=False` (état par défaut sûr).
2. Écrire du texte invalide dans `state.json` (ex: `{pas du json`) puis
   relancer : warning « state.json illisible ou corrompu » dans les logs et
   état par défaut (aucune position), sans plantage.