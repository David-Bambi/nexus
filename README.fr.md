# Nexus

*[English version](README.md)*

Un gestionnaire de projets mono-utilisateur, inspiré de GTD, servi comme application web locale.

## Prérequis

- Python >= 3.12
- [`uv`](https://docs.astral.sh/uv/) pour gérer les dépendances

## Développement

```bash
uv sync                                          # installe les dépendances de pyproject.toml / uv.lock
NEXUS_DATABASE_URL=sqlite:///instance/nexus.db \
  FLASK_APP=src.app:create_app uv run flask run  # serveur de dév sur le port 5000, base de brouillon
uv run pytest                                    # lance les tests
```

Sans `NEXUS_DATABASE_URL`, `flask run` utilise la vraie base dans
`~/.nexus/`. Les migrations sont appliquées automatiquement au démarrage.

## Lancer comme service

L'application écoute sur `http://127.0.0.1:8765` et nulle part ailleurs : elle
n'a pas d'authentification, donc l'adresse ne peut pas être changée.

```bash
uv run python -m src.main                          # lance au premier plan
uv run python scripts/install_service.py install   # démarre automatiquement à l'ouverture de session
uv run python scripts/install_service.py uninstall # arrête et retire le service (les données restent)
```

| Système | Ce que crée `install` |
|---|---|
| Linux | unité systemd utilisateur `~/.config/systemd/user/nexus.service` (`Restart=on-failure`) |
| macOS | agent launchd `~/Library/LaunchAgents/com.nexus.app.plist` (`KeepAlive`) |
| Windows | tâche planifiée `nexus`, à l'ouverture de session, relancée jusqu'à 3 fois en cas d'échec |

Seul Linux a été vérifié sur une vraie machine. Les définitions macOS et
Windows sont générées et testées unitairement, mais n'ont jamais été lancées :
attendez-vous à devoir les ajuster. Sous Windows, `NEXUS_HOME` n'est pas
transmis à la tâche.

Le service démarre quand vous vous connectez. Pour le démarrer au boot sans
connexion (Linux), lancez une fois :

```bash
loginctl enable-linger
```

Gérez-le avec `systemctl --user status nexus`, `restart nexus`, `stop nexus`.

### Déployer la copie de travail (Linux)

```bash
scripts/deploy.sh          # refuse un arbre git modifié
scripts/deploy.sh --force  # déploie malgré des changements non commités
```

Lance `uv run pytest -q`, `uv sync --frozen`, puis
`systemctl --user restart nexus`, et interroge `http://127.0.0.1:8765/`
pendant 20 s au plus. En cas d'échec, il affiche les 20 dernières lignes du
journal et sort avec une erreur. La sauvegarde et les migrations ont lieu au
démarrage de l'application, comme d'habitude. Le nom du service (`nexus`) et
l'URL sont codés en dur : si vous avez changé `NEXUS_PORT`, la vérification
expirera alors que le service tourne.

## Ligne de commande

`scripts/install_cli.sh install` place une commande `nexus` éditable dans
`~/.local/bin` (le dossier d'outils de uv) : elle marche depuis n'importe quel
dossier, sans `uv run`. Elle suit la copie de travail : réinstallez seulement
si vous déplacez le dépôt. `scripts/install_cli.sh uninstall` la retire. Sans
l'installation, `uv sync` et `uv run nexus ...` marchent pareil. La CLI
utilise la même base que le service (`NEXUS_HOME` / `NEXUS_DATABASE_URL`
s'appliquent). Les tâches et les versions ont des références courtes
(`t-4k2`, `v-9xa`), visibles aussi dans l'interface web. Les exemples
ci-dessous utilisent `uv run` ; retirez-le si `nexus` est installé.

```bash
uv run nexus tasks                          # aussi : versions, projects, version
uv run nexus NX                             # détail d'un projet (par clé)
uv run nexus NX 1.0                         # détail d'une version, tâches, définition de terminé
uv run nexus NX 1.0 check 2                 # aussi : uncheck <n>, start, release, add-/edit-/remove-criterion (ou après une réf v-)
uv run nexus t-4k2                          # détail d'une tâche (ou une réf v-)
uv run nexus add task NX 1.0 -t "Titre" -s S  # tâche planifiée ; sans version, elle va dans l'inbox
uv run nexus "acheter un câble USB-C"       # capture dans l'inbox
uv run nexus import plan.json --dry-run     # importe projets/versions/tâches, tout ou rien
uv run nexus import - --text < idees.txt    # une tâche d'inbox par ligne
```

Codes de sortie : 0 ok, 1 refusé par une règle des données, 2 ligne de
commande incorrecte. La CLI ne peut pas modifier les tâches ni changer leur
état (le serveur MCP le peut). Elle applique les migrations en attente au
démarrage : elle peut donc mettre à jour la vraie base avant le redéploiement
du service. Format d'import et détails : `docs/functional/cli.md`.

## Serveur MCP

Le service parle aussi le Model Context Protocol : un assistant IA peut lire
et modifier vos projets (29 outils : lister, afficher, chercher, capturer,
ajouter, modifier, planifier, démarrer, terminer, bloquer, publier, éditer la
définition de terminé, importer, paramètres et profil d'utilisation de
l'IA...). Enregistrez-le une fois dans Claude Code :

```bash
claude mcp add --transport http nexus http://127.0.0.1:8765/mcp
```

Les outils en lecture seule peuvent être autorisés d'office ; les outils
d'écriture demandent une approbation, et leurs événements sont journalisés
avec l'acteur `mcp`. Supprimer des tâches, des versions ou des projets, et
archiver, restent dans l'interface web. Sécurité : le point d'accès n'a pas
d'authentification et repose sur l'écoute en boucle locale plus une
vérification Host/Origin/Content-Type ; il est indisponible quand le service
est arrêté. Outils et règles : `docs/functional/mcp.md`.

## Configuration

Variables d'environnement, toutes facultatives (voir `.env.example`) :

| Variable | Défaut | Rôle |
|---|---|---|
| `NEXUS_HOME` | `~/.nexus` | Dossier de la base, du journal et des sauvegardes |
| `NEXUS_DATABASE_URL` | `sqlite:///<NEXUS_HOME>/data.db` | URL complète de la base, remplace le fichier par défaut |
| `NEXUS_PORT` | `8765` | Port d'écoute |
| `NEXUS_SECRET_KEY` | `dev` | Clé de signature Flask |

## Données, journaux et sauvegardes

Tout est dans `NEXUS_HOME` (`~/.nexus` par défaut) :

| Chemin | Contenu |
|---|---|
| `data.db` | La base SQLite (mode WAL : `data.db-wal` et `data.db-shm` sont à côté) |
| `app.log` | Journal de l'application, tourné à 1 Mo, 5 anciens fichiers gardés. Aussi dans `journalctl --user -u nexus` sous Linux |
| `backups/` | `data-YYYYmmdd-HHMMSS.db`, une par démarrage, les 14 plus récentes gardées |

Une sauvegarde est faite à chaque démarrage, avant les migrations : une mise à
jour ratée peut donc toujours être annulée. Les sauvegardes ont lieu
**seulement au démarrage** : une machine allumée pendant des semaines n'a pas
de nouvelle copie entre-temps. Pour une copie à tout moment, téléchargez
`http://127.0.0.1:8765/export.json` (toute la base en JSON ; la
`definition_of_done` de chaque version est une liste d'objets
`{"description", "done"}`).

### Restaurer une sauvegarde

```bash
systemctl --user stop nexus                      # ou arrêtez le processus au premier plan
cp ~/.nexus/backups/data-YYYYmmdd-HHMMSS.db ~/.nexus/data.db
rm -f ~/.nexus/data.db-wal ~/.nexus/data.db-shm  # restes de la base remplacée
systemctl --user start nexus                     # les migrations en attente sont appliquées au démarrage
```

### Récupérer les données de la base de développement

Les données créées avant l'existence de `~/.nexus` sont dans
`instance/nexus.db`. Sans serveur lancé :

```bash
mkdir -p ~/.nexus && cp instance/nexus.db ~/.nexus/data.db
```

## Documentation

`docs/` est la source de vérité (architecture, ADR, maquettes fonctionnelles,
référence). Pour la construire ou la servir en local :

```bash
uv run mkdocs serve
```

## Utilisation de l'IA

Ce projet a été réalisé avec l'aide d'un assistant IA, Claude (Anthropic), par Claude Code, de
septembre à novembre 2026. Le tableau ci-dessous montre à quel point chaque partie en dépend.

- 🤖 **Fait par l'IA** : l'IA a produit le contenu ; je l'ai dirigée et j'ai relu.
- 🤝 **Avec l'aide de l'IA** : j'ai fait le travail ; l'IA a proposé, expliqué, révisé ou corrigé.
- ✋ **Sans IA** : fait entièrement par moi.

| Domaine | Niveau | Concrètement |
|---|---|---|
| Gestion de projet | 🤖 Fait par l'IA | Spécifications, plans, versions et tâches |
| Conception et architecture | 🤖 Fait par l'IA | Découpage en couches, modèle de données et ADR |
| Code | 🤖 Fait par l'IA | Application web, services, CLI et serveur MCP |
| Commentaires du code | 🤖 Fait par l'IA | Docstrings et commentaires |
| Tests | 🤖 Fait par l'IA | La suite pytest |
| Documentation et README | 🤖 Fait par l'IA | Site `docs/` et ce README |
| Assets graphiques | 🤖 Fait par l'IA | Feuille de style et mise en page |
| Outils | 🤖 Fait par l'IA | Scripts du service, de la CLI et du déploiement |
