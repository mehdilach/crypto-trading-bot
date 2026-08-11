# Déploiement Render — crypto-trading-bot

Procédure de référence, telle que validée pendant le chantier (crash-test Turso local passé,
code poussé sur GitHub, déploiement cloud mis en pause faute de plan gratuit).

## État de la décision

- Le plan **Free de Render n'est plus proposé pour les nouveaux services** (changement de
  politique : seuls les anciens services le conservent). Créer ce Background Worker implique
  un plan payant (**Starter : 7 $/mois**, carte bancaire requise).
- Décision : rester en local pour l'instant. Le code est identique en local et sur Render
  (même base Turso, même testnet Binance) ; reprendre cette procédure le jour où un
  hébergement 24/7 redevient pertinent.

## Prérequis

- Repo GitHub : `https://github.com/mehdilach/crypto-trading-bot` (branche `main`)
- Base Turso dédiée : `crypto-trading-bot-state` (compte `mehdilach`),
  URL `libsql://crypto-trading-bot-state-mehdilach.aws-eu-west-1.turso.io`
- Les 8 variables d'environnement sont reprises depuis le `.env` local
  (jamais commité ; template dans `.env.example`)

## Création du service sur le dashboard Render

1. **New → Background Worker** (pas un Web Service)
2. **Connect repository** : `mehdilach/crypto-trading-bot`, branche `main`
3. Langage : **Python 3** ; région : Oregon (US West) — sans importance (Turso passe en HTTPS)
4. **Instance Type** : Starter (ou supérieur selon besoin. Pas de Free : plus disponible pour
   les nouveaux services depuis ~2026)
5. **Build Command** :
   ```
   pip install -r requirements.txt
   ```
6. **Start Command** :
   ```
   python main.py
   ```
7. **Environment Variables** (8, à saisir manuellement — valeurs dans `.env` local) :
   - `BINANCE_API_KEY`
   - `BINANCE_API_SECRET`
   - `USE_TESTNET=true`
   - `SYMBOL=BTC/USDT`
   - `MAX_ORDER_SIZE=50`
   - `STOP_LOSS_PCT=2.0`
   - `TURSO_DATABASE_URL=libsql://crypto-trading-bot-state-mehdilach.aws-eu-west-1.turso.io`
   - `TURSO_AUTH_TOKEN`
8. **Deploy**

## Vérification après déploiement (onglet Logs)

Attendu dès le démarrage :

```
[INFO] crypto-bot.state: Mode stockage: TURSO distant (libsql://crypto-trading-bot-state-mehdilach.aws-eu-west-1.turso.io)
[INFO] crypto-bot.exchange: Mode TESTNET actif — aucun ordre réel ne sera passé.
[INFO] crypto-bot.main: Bot démarré — symbole=BTC/USDT, testnet=True
[INFO] crypto-bot.main: Signal=hold, position=False — rien à faire.   (toutes les ~60 s)
```

Et après un BUY :

```
[INFO] crypto-bot.exchange: Ordre BUY BTC/USDT — montant ~50.00 ...
[INFO] crypto-bot.main: Position ouverte — entrée à XXXX.XX, état sauvegardé.
```

**Redémarrage automatique après crash** : comportement par défaut de Render
(Restart Policy = « On Failure » dans Settings → Runtime ; inutile de le configurer).

Si aucune ligne « Mode stockage » n'apparaît : vérifier les 8 variables (une valeur vide
bascule silencieusement en mode fichier local, ce qui est perdu à chaque redéploiement).

## Croissance et déploiements suivants

- Chaque push sur `main` déclenche un auto-deploy (Auto-Deploy activé par défaut).
- La base Turso étant distante, redéploiements et redémarrages ne perdent jamais l'état
  (position ouverte, prix d'entrée) — c'est l'objet de `state_manager.py`.
- Pour modifier les paramètres (STOP_LOSS_PCT, MAX_ORDER_SIZE...) : passer par le dashboard
  Render, pas par le code.