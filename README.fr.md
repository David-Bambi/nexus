# Nexus

*[English version](README.md)*

Un gestionnaire de projets personnel, inspiré de GTD, servi comme application
web locale.

Le travail forme un arbre : projet → sous-projets (un niveau) →
fonctionnalités (à toute profondeur) → tâches. Chaque projet a une version
calculée `MAJEURE.MINEURE` : la mineure monte toute seule quand une
fonctionnalité est terminée ; la majeure monte à la main une fois tous ses
critères majeurs cochés.

## Prérequis

- Python >= 3.12
- [`uv`](https://docs.astral.sh/uv/) pour gérer les dépendances

## Développement

```bash
uv sync                                          # installe les dépendances de pyproject.toml / uv.lock
NEXUS_DATABASE_URL=sqlite:///instance/nexus.db \
  FLASK_APP=src.app:create_app uv run flask run  # serveur de dev sur le port 5000, base jetable
uv run pytest                                    # lance les tests
```

Sans `NEXUS_DATABASE_URL`, `flask run` utilise la vraie base dans
`~/.nexus/`. Les migrations s'appliquent toutes seules au démarrage. La base
de développement doit être neuve : un `instance/nexus.db` laissé par la 1.x
est refusé (voir « Passer de la 1.x ») ; supprime-le et recommence.

## Lancer comme service

L'application écoute sur `http://127.0.0.1:8765` et nulle part ailleurs :
elle n'a pas d'authentification, donc l'adresse ne peut pas changer.

```bash
uv run python -m src.main                          # lance au premier plan
uv run python scripts/install_service.py install   # démarre à l'ouverture de ta session
uv run python scripts/install_service.py uninstall # arrête et retire le service (les données restent)
```

| Système | Ce que crée `install` |
|---|---|
| Linux | unité systemd utilisateur `~/.config/systemd/user/nexus.service` (`Restart=on-failure`) |
| macOS | agent launchd `~/Library/LaunchAgents/com.nexus.app.plist` (`KeepAlive`) |
| Windows | tâche planifiée `nexus`, à l'ouverture de session, relancée jusqu'à 3 fois en cas d'échec |

Seul Linux a été vérifié sur une vraie machine. Les définitions macOS et
Windows sont générées et testées unitairement, mais n'ont pas tourné :
attends-toi à les ajuster. Sous Windows, `NEXUS_HOME` n'est pas transmis à la
tâche.

Le service démarre quand tu ouvres ta session. Pour le démarrer au boot sans
session ouverte (Linux), lance une fois :

```bash
loginctl enable-linger
```

Pilote-le avec `systemctl --user status nexus`, `restart nexus`, `stop nexus`.

### Déployer la copie de travail (Linux)

```bash
scripts/deploy.sh          # refuse un arbre git modifié
scripts/deploy.sh --force  # déploie malgré des changements non commités
```

Lance `uv run pytest -q`, `uv sync --frozen`, puis
`systemctl --user restart nexus`, et interroge `http://127.0.0.1:8765/`
pendant 20 s au plus. En cas d'échec, il affiche les 20 dernières lignes du
journal et sort en erreur. La sauvegarde et les migrations se font au
démarrage de l'application, comme d'habitude. Le nom du service (`nexus`) et
l'URL sont fixés : si tu as changé `NEXUS_PORT`, la vérification expirera
même si le service tourne.

## Ligne de commande

`scripts/install_cli.sh install` installe une commande `nexus` éditable dans
`~/.local/bin` (le dossier des outils de uv) : elle marche depuis n'importe
quel dossier, sans `uv run`. Elle suit la copie de travail : réinstalle-la
seulement si tu déplaces le dépôt. `scripts/install_cli.sh uninstall` la
retire. Sans installation, `uv sync` puis `uv run nexus ...` marchent pareil.
La CLI utilise la même base que le service (`NEXUS_HOME` et
`NEXUS_DATABASE_URL` s'appliquent). Les projets racines se nomment par leur
clé ; les sous-projets, fonctionnalités et tâches ont des références courtes
(`s-…`, `f-…`, `t-…`), visibles aussi dans l'interface web. Les exemples
ci-dessous utilisent `uv run` ; retire-le si `nexus` est installé.

```bash
uv run nexus projects                       # projets et sous-projets actifs, avec leur version
uv run nexus tasks                          # toutes les fonctionnalités et tâches
uv run nexus NX --all                       # détail d'un projet (clé ou réf. s-) : version, critères, arbre
uv run nexus f-4k2                          # détail d'une fonctionnalité ou tâche (réf. f- ou t-)
uv run nexus add feature NX -t "Titre"      # aussi : add task NX -p f-4k2 -t "Titre" -s S
uv run nexus "acheter un câble USB-C"       # capture dans l'inbox
uv run nexus state t-4k2 done               # change d'état, étape par étape (--reason pour waiting)
uv run nexus import plan.json --dry-run     # importe des projets et leurs arbres, tout ou rien
uv run nexus import - --text < idees.txt    # une tâche d'inbox par ligne
uv run nexus export features -o features.json  # export des fonctionnalités lu par metrique (nexus.features/1)
uv run nexus version                        # version du paquet installé
```

Codes de sortie : 0 ok, 1 refusé par une règle des données, 2 ligne de
commande fausse. La CLI lit, capture, ajoute, change d'état, importe et
exporte ; elle ne peut ni modifier ni déplacer les éléments, ni modifier les
critères, ni sortir une version majeure (l'interface web et le serveur MCP le
peuvent). Elle applique les migrations en attente au démarrage : elle peut
donc mettre à jour la vraie base avant le redéploiement du service. Format
d'import et détails : `docs/concept/nexus/interfaces/cli/` et
`docs/concept/nexus/interfaces/import/`.

## Serveur MCP

Le service en marche parle aussi le Model Context Protocol : un assistant IA
peut lire et modifier tes projets (33 outils : lister, lire, chercher,
tableau de bord, capturer, ajouter, clarifier, déplacer, réordonner, changer
de nature, modifier, changements d'état, édition des projets et des critères,
version majeure, import). Enregistre-le une fois dans Claude Code :

```bash
claude mcp add --transport http nexus http://127.0.0.1:8765/mcp
```

Les outils en lecture peuvent être autorisés d'office ; les outils en
écriture demandent une approbation, et leurs événements sont journalisés avec
l'acteur `mcp`. Supprimer des éléments ou des projets et archiver restent
dans l'interface web. Sécurité : le point d'accès n'a pas d'authentification
et repose sur l'écoute en boucle locale plus une vérification
Host/Origin/Content-Type ; il est indisponible quand le service est arrêté.
Outils et règles : `docs/concept/nexus/interfaces/mcp/`.

## Configuration

Variables d'environnement, toutes facultatives (voir `.env.example`) :

| Variable | Défaut | Rôle |
|---|---|---|
| `NEXUS_HOME` | `~/.nexus` | Dossier de la base, du journal et des sauvegardes |
| `NEXUS_DATABASE_URL` | `sqlite:///<NEXUS_HOME>/data.db` | URL complète de la base, remplace le fichier par défaut |
| `NEXUS_PORT` | `8765` | Port d'écoute |
| `NEXUS_SECRET_KEY` | `dev` | Clé de signature Flask |

## Données, journaux et sauvegardes

Tout vit dans `NEXUS_HOME` (`~/.nexus` par défaut) :

| Chemin | Contenu |
|---|---|
| `data.db` | La base SQLite (mode WAL, donc `data.db-wal` et `data.db-shm` à côté) |
| `app.log` | Journal de l'application, tourné à 1 Mo, 5 anciens fichiers gardés. Aussi dans `journalctl --user -u nexus` sous Linux |
| `backups/` | `data-AAAAmmjj-HHMMSS.db`, un par démarrage, les 14 plus récents gardés |

Une sauvegarde est prise à chaque démarrage, avant les migrations : une mise
à jour ratée peut donc toujours être annulée. Les sauvegardes se font
**seulement au démarrage** : une machine allumée des semaines n'a pas de
nouvelle copie entre-temps. Pour une copie à tout moment, télécharge
`http://127.0.0.1:8765/export.json` (toute la base en JSON : projets avec leur
version, fonctionnalités et tâches, étiquettes, critères majeurs et
événements). C'est une sauvegarde, pas un format d'import.

### Restaurer une sauvegarde

```bash
systemctl --user stop nexus                      # ou arrête le processus au premier plan
cp ~/.nexus/backups/data-AAAAmmjj-HHMMSS.db ~/.nexus/data.db
rm -f ~/.nexus/data.db-wal ~/.nexus/data.db-shm  # restes de la base remplacée
systemctl --user start nexus                     # les migrations en attente s'appliquent au démarrage
```

### Passer de la 1.x

Nexus 2.0 a remplacé les versions planifiées par un arbre projet /
fonctionnalité / tâche et a recommencé son historique de migrations : il
refuse de démarrer sur une base 1.x et le dit. Archive l'ancienne base, puis
redémarre sur une base vide :

```bash
systemctl --user stop nexus
mkdir -p ~/.nexus/archive
mv ~/.nexus/data.db ~/.nexus/archive/data-1.x.db
rm -f ~/.nexus/data.db-wal ~/.nexus/data.db-shm
systemctl --user start nexus                     # crée une base 2.0 vide
```

Rien n'est migré : les données 1.x restent lisibles dans le fichier archivé
(et dans un export JSON pris avant la mise à jour).

## Utilisation de l'IA

Ce projet a été fait avec un assistant IA, Claude (Anthropic), par Claude
Code, de septembre à novembre 2026. Le tableau ci-dessous montre à quel point
chaque partie en dépend. La page d'un projet montre aussi, par catégorie, la
part des lignes ajoutées dans des commits co-signés par Claude.

- 🤖 **Fait par l'IA** : l'IA a produit le contenu ; je l'ai dirigée et j'ai relu.
- 🤝 **Avec l'aide de l'IA** : j'ai fait le travail ; l'IA a proposé, expliqué, révisé ou corrigé.
- ✋ **Sans IA** : fait entièrement par moi.

| Domaine | Niveau | Concrètement |
|---|---|---|
| Gestion de projet | 🤖 Fait par l'IA | Specs, plans, fonctionnalités, tâches et critères |
| Conception et architecture | 🤖 Fait par l'IA | Couches, modèle de données et décisions de la carte Concept |
| Code | 🤖 Fait par l'IA | Application web, services, CLI et serveur MCP |
| Commentaires du code | 🤖 Fait par l'IA | Docstrings et commentaires |
| Tests | 🤖 Fait par l'IA | La suite pytest |
| Documentation et README | 🤖 Fait par l'IA | Carte Concept, site MkDocs et ces README |
| Assets graphiques | 🤖 Fait par l'IA | Feuille de style, mise en page, schémas et captures |
| Outils | 🤖 Fait par l'IA | Scripts de service, de CLI et de déploiement |

## Documentation

`docs/` est la source de vérité. La documentation du projet (modèle, journal
d'événements, interfaces, exploitation, mesure, guides) est une carte Concept
en français, dans `docs/concept/` (racine `docs/concept/nexus/nexus.cpt`) :
ouvre-la dans Concept, entrée « Nexus ».

Le site MkDocs couvre seulement le code (explications Python, outils IA,
référence de l'API générée depuis les docstrings). Pour le construire ou le
servir en local :

```bash
uv run mkdocs serve
```
