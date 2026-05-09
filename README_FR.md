[HHC-N818OP photo]: doc/img/HHC-N8I8OP_Stock_Photo.jpg

# HHC-N818OP Standalone Client

Un client standalone pour gérer les relais HHC-N818OP avec support de plugins et scénarios programmables.

![HHC-N818OP photo]

## Description

Ce projet fournit un client daemon autonome pour contrôler les modules de relais HHC-N818OP via le réseau. Il permet de:

- Piloter des relais individuellement ou par groupes
- Définir des scénarios temporisés avec activation/désactivation programmée
- Intégrer des plugins externes (MQTT, HTTP, Meross IoT, etc.)
- Gérer les dépendances entre relais (ex: pompe de puits)

## Quickstart

### Installation avec pip

```bash
git clone https://github.com/yannick-lidie/hhc-n818op-standalone.git
cd hhc-n818op-standalone
python -m pip install .
```

### Installation avec uv

```bash
git clone https://github.com/yannick-lidie/hhc-n818op-standalone.git
cd hhc-n818op-standalone
uv pip install .
```

### Lancer le daemon

```bash
cp daemon_hhc_n818op/hhc_n818op_standalone_d.yaml daemon_hhc_n818op/hhc_n818op_standalone_d.local.yaml
python daemon_hhc_n818op/hhc_n818op_standalone_d.py
```

### Lancer avec Docker (`start.sh`)

```bash
cd docker/bin
./start.sh
```

> **Note** : Le script `start.sh` crée automatiquement le fichier `docker/.env` depuis `docker/.env.in` s'il n'existe pas.

Pour la configuration Docker complète, voir [Installation avec Docker](#installation-avec-docker).

## Fonctionnalités

### Gestion des relais

- Contrôle de 8 relais via connexion réseau
- Activation/désactivation individuelle ou groupée
- État des relais en temps réel

### Scénarios programmables

- Définition d'horaires de démarrage précis
- Durées configurables pour chaque relais
- Exécution séquentielle ou parallèle
- Support des formats de temps : `HH:MM:SS.microsecondes`

### Système de plugins

- Architecture modulaire pour étendre les fonctionnalités
- Support natif des plugins MQTT (Meross IoT)
- Gestion des dépendances entre équipements
- Intégration flexible via configuration YAML

## Prérequis

- Python 3.10+
- Bibliothèques requises (voir `pyproject.toml`) :
  - `requests`
  - `ruamel.yaml`
  - `pytz`
  - `meross-iot`

## Installation

Pour la mise en route la plus rapide, voir la section [Quickstart](#quickstart) ci-dessus.

### Cloner le dépôt

```bash
git clone https://github.com/yannick-lidie/hhc-n818op-standalone.git
cd hhc-n818op-standalone
```

### Installer les dépendances

```bash
make dev # créé l'environnement Python avec les dépendances

# ou alors

# Créer un environnement virtuel (recommandé)
python -m pip install pipx

pipx install uv

# Installer les dépendances
uv sync

source .venv/bin/activate  # Linux/Mac
# .\.venv\Scripts\activate  # Windows
```

## Configuration

Copier et adapter le fichier de configuration :

```bash
cp daemon_hhc_n818op/hhc_n818op_standalone_d.yaml daemon_hhc_n818op/hhc_n818op_standalone_d.local.yaml
```

Éditer le fichier pour configurer :

- Adresse IP et port du module HHC-N818OP
- Paramètres du daemon (niveau de log, fichiers PID, timezone)
- Scénarios de relais
- Configuration des plugins

## Configuration détaillée

### Structure du fichier YAML

```yaml
daemon:
  log_level: info           # Niveau de logging (debug, info, warning, error)
  pidfile: /run/hhc_n818op_d.pid  # Fichier PID
  cycle: 2                  # Cycle de vérification (secondes)
  cycle_sleeping: 300       # Temps d'attente entre cycles (secondes)
  logfile: /var/log/daemon_hhc_n818op.log
  timezone: Europe/Paris    # Fuseau horaire

hhc-n818op:
  host: 10.0.30.2           # Adresse IP du module HHC-N818OP
  port: 5000                # Port de connexion

relays_scenarios: # Liste des scénarios
  - start_time: '23:16:00'
    relays_durations: # Séquence d'activation
      - 1: '00:00:10'       # Relais 1 pendant 10 secondes
        5: '00:00:10'       # Relais 5 pendant 10 secondes (parallèle)
      - 1: '00:00:10'
        2: '00:00:10'

# Comment this section if you don't use plugins
plugin_relays: # Configuration de plugins additionnels pour déclencher d'autres relais hardware par dépendances.
  dependencies_mapping:
    2: Well Pump            # Le relais 2 déclenche un autre relais dépendant nommé "Well Pump"

  dependencies:
    Well Pump: # Relais switch dépendant de type Meross IoT
      host: 10.0.30.8
      port: 80
      triggers:
        mqtt:
          plugin_module: plugins.meross.meross_client_cloud_mqtt
          plugin_classname: PluginMeross
```

### Options des scénarios

- `start_time`: Heure de démarrage du scénario. **Formats de date/heure supportés (toutes combinaisons):**
  - Complet: `JJ/MM/AAAA HH:MM:SS.microsecondes` (ex: `15/01/2024 14:30:45.123456`)
  - Date + Heure: `JJ/MM/AAAA HH:MM:SS` (ex: `15/01/2024 14:30:45`)
  - Date seulement: `JJ/MM/AAAA` (ex: `15/01/2024`)
  - Heure + Microsecondes: `HH:MM:SS.microsecondes` (ex: `14:30:45.123456`)
  - Heure seulement: `HH:MM:SS` (ex: `14:30:45`)
  - Microsecondes seulement: `.microsecondes` (ex: `.123456`)
  - Les parties `date` et `heure` sont optionnelles. Les microsecondes supportent 1 à 6 chiffres.
- `relays_durations`: Liste de dictionnaires où:
  - Clé = numéro de relais (1-8)
  - Valeur = durée d'activation (format: `HH:MM:SS`)
  - Les relais sur la même ligne sont activés en parallèle

### Configuration de périodicité

La section `periodicity` contrôle combien de temps les relais par défaut restent activés après la fin du dernier scénario.

**Stratégies disponibles :**

| Stratégie      | Description                                             | Exemple de valeur                     |
|----------------|---------------------------------------------------------|---------------------------------------|
| `end_of_day`   | Jusqu'à minuit du même jour (par défaut)                | `end_of_day`                          |
| `end_of_week`  | Jusqu'à la fin de la semaine en cours (dimanche minuit) | `end_of_week`                         |
| `end_of_month` | Jusqu'à la fin du mois en cours                         | `end_of_month`                        |
| `custom_days`  | Durée ou date/heure personnalisée                       | `3` ou `"02:00:00"` ou `"01/01/2025"` |

**Exemple de configuration :**
```yaml
periodicity:
  mask_end_strategy: end_of_day  # Stratégie à utiliser
  custom_days: 1                # Requis lorsque la stratégie est custom_days
```

**Constantes Python :**
Les constantes suivantes sont disponibles dans `daemon_hhc_n818op` pour une utilisation programmatique :
- `MASK_END_STRATEGY_END_OF_DAY`
- `MASK_END_STRATEGY_END_OF_WEEK`
- `MASK_END_STRATEGY_END_OF_MONTH`
- `MASK_END_STRATEGY_CUSTOM_DAYS`
- `CUSTOM_DAYS`
- `MASK_END_STRATEGY`

## Utilisation

### Démarrer le daemon

```bash
python daemon_hhc_n818op/hhc_n818op_standalone_d.py
```

### Installation avec Docker

Le projet fournit un script `start.sh` et un fichier `docker-compose.yaml` pour un déploiement simplifié en conteneur.

#### Prérequis

- Docker installé
- Docker Compose (v2+)
- Utilisateur avec permissions Docker

#### Configuration Docker

1. **Configurer l'environnement** : Le script `start.sh` génère automatiquement le fichier `docker/.env` depuis `docker/.env.in` avec les valeurs par défaut. Vous pouvez modifier ces valeurs :
   ```bash
   # Fichier docker/.env.in (valeurs par défaut)
   CONTAINER_NAME=hhc_n818op/relay_client
   INSTALL_FOLDER_CLIENT=/usr/share/${CONTAINER_NAME}
   CONTAINER_USER=hhc_n818op_user
   CONTAINER_NETWORK=hhc_n818op_network
   UID_GID_DEFAULT=1000
   ```

   > **Astuce** : Pour personnaliser, modifiez directement le fichier `docker/.env` généré par `start.sh`.

#### Démarrer le service

```bash
# Se positionner dans le dossier docker/bin
cd docker/bin

# Exécuter le script de démarrage (crée le réseau, construit l'image et lance le conteneur)
./start.sh
```

Le script `start.sh` effectue automatiquement :

- La création du réseau Docker `hhc_n818op_network` (s'il n'existe pas)
- La création de l'utilisateur système dédié (si nécessaire)
- L'arrêt du conteneur existant
- La reconstruction et le démarrage du conteneur avec `docker-compose.yaml`

#### Commandes Docker utiles

```bash
# Arrêter le conteneur
docker stop hhc_n818op_client

# Voir les logs
docker logs hhc_n818op_client -f

# Redémarrer le conteneur
docker restart hhc_n818op_client

# Supprimer le conteneur et le réseau
docker compose -f ../docker-compose.yaml down

# Reconstruire l'image (après modification du code)
docker compose -f ../docker-compose.yaml build --no-cache

# Accéder au shell du conteneur
docker exec -it hhc_n818op_client sh
```

#### Configuration Docker avancée

Le `Dockerfile` (dans `docker/Dockerfile`) utilise :

- **Image base** : `python:3.11-alpine`
- **Répertoire de travail** : `${INSTALL_FOLDER_CLIENT}` (par défaut `/usr/share/hhc_n818op/relay_client`)
- **PYTHONPATH** : Défini sur `${INSTALL_FOLDER_CLIENT}` pour permettre les imports Python
- **Point d'entrée** : `sh -c "export PYTHONPATH=$(pwd) && python hhc_n818op_standalone_d.py"`
- **Fichiers système créés** : `/var/log/daemon_hhc_n818op.log` et `/run/hhc_n818op_d.pid` avec permissions `666`
- **Dépendances Python** : `requests`, `ruamel.yaml`, `pytz`, `meross-iot`

Pour modifier l'image, éditer le `Dockerfile` puis reconstruire avec la commande ci-dessus.

#### Variables d'environnement Docker

| Variable                | Description                                 | Valeur par défaut                       |
|-------------------------|---------------------------------------------|-----------------------------------------|
| `CONTAINER_NAME`        | Nom de l'image/container Docker             | `hhc_n818op/relay_client`               |
| `INSTALL_FOLDER_CLIENT` | Répertoire d'installation dans le conteneur | `/usr/share/${CONTAINER_NAME}`          |
| `CONTAINER_NETWORK`     | Nom du réseau Docker                        | `hhc_n818op_network`                    |
| `WRK_DOCKER_DIR`        | Répertoire Docker (généré par `start.sh`)   | Chemin absolu du dossier `docker/`      |
| `PUID`/`PGID`           | UID/GID de l'utilisateur                    | `1000` (ou depuis `${UID_GID_DEFAULT}`) |

#### Commandes Docker utiles

```bash
# Arrêter le conteneur
docker stop hhc_n818op/relay_client

# Voir les logs
docker compose -f docker/docker-compose.yaml logs -f hhc_n818op_client

# Redémarrer le conteneur
docker restart hhc_n818op_client

# Supprimer le conteneur et le réseau
cd docker && docker compose -f docker-compose.yaml down

# Reconstruire l'image (après modification du code)
cd docker && docker compose -f docker-compose.yaml build --no-cache

# Vérifier la configuration Docker résolue
docker compose -f docker/docker-compose.yaml config

# Accéder au shell du conteneur
docker exec -it docker-hhc_n818op_client-1 sh
```

#### Dépannage Docker

**Problème : `Cannot locate Dockerfile` ou `path not found`**

- **Cause** : Le `build.context` dans `docker-compose.yaml` est incorrect.
- **Solution** : Vérifiez que `context: ${WRK_DOCKER_DIR}/../` pointe bien vers la racine du projet (`hhc-n818op-standalone/`).
- **Vérification** : Lancez `docker compose -f docker/docker-compose.yaml config` pour voir le contexte résolu.

**Problème : `ModuleNotFoundError: No module named 'daemon_hhc_n818op'`**

- **Cause** : Le package Python `daemon_hhc_n818op` n'est pas dans le PYTHONPATH.
- **Solution** : Le Dockerfile définit maintenant `ENV PYTHONPATH=${INSTALL_FOLDER_CLIENT}` et l'ENTRYPOINT exporte dynamiquement `PYTHONPATH=$(pwd)`. Reconstruisez l'image avec `--no-cache`.

**Problème : `Permission denied: '/var/log/daemon_hhc_n818op.log'` ou `/run/hhc_n818op_d.pid'`**

- **Solution** : Le Dockerfile crée maintenant ces fichiers avec `chmod 666` pendant le build. Reconstruisez l'image avec `--no-cache`.

**Problème : Le conteneur redémarre en boucle**

- **Cause** : Une erreur non gérée dans l'application (ex: erreur de configuration YAML).
- **Diagnostic** : `docker compose -f docker/docker-compose.yaml logs hhc_n818op_client`
- **Solution** : Corrigez la configuration (ex: vérifiez que `plugin_relays.dependencies` existe dans votre YAML).

## Structure du projet

```
hhc-n818op-standalone/
├── daemon_hhc_n818op/
│   ├── __init__.py                    # Constantes communes
│   ├── hhc_n818op/
│   │   ├── __init__.py                # Constantes du module relais
│   │   ├── relay_client.py            # Client principal des relais
│   │   ├── relay_plugins.py           # Gestion des plugins
│   │   └── time_parser.py             # Parseur de temps
│   ├── hhc_n818op_standalone_d.py      # Point d'entrée du daemon
│   └── hhc_n818op_standalone_d.yaml    # Configuration par défaut
├── docker/
│   ├── .env.in                        # Template de configuration Docker
│   ├── .env                           # Configuration Docker (généré par start.sh)
│   ├── Dockerfile                     # Définition de l'image Docker
│   ├── bin/
│   │   └── start.sh                   # Script de démarrage
│   └── docker-compose.yaml            # Configuration Docker Compose
├── plugins/
│   └── meross/
│       └── meross_client_cloud_mqtt.py  # Plugin Meross IoT
├── tests/
│   └── ...                            # Tests unitaires
├── pyproject.toml                     # Configuration du projet
├── README_FR.md                       # Documentation en français
└── LICENSE                            # Licence GPL-3.0
```

## Plugins disponibles

### Plugin Meross MQTT

Permet de contrôler des équipements Meross IoT via MQTT et de les intégrer comme dépendances pour les relais.

**Configuration :**

```yaml
plugin_module: plugins.meross.meross_client_cloud_mqtt
plugin_classname: PluginMeross
```

## Développement

### Ajouter un nouveau plugin

1. Créer un module dans le dossier `plugins/`
2. Implémenter une classe qui hérite de `BasePlugin` (voir `relay_plugins.py`)
3. Implémenter les méthodes requises :
  - `start()`: Démarrage du plugin
  - `stop()`: Arrêt du plugin
  - `is_ready()`: Vérification que le plugin est prêt
  - `get_device_status(device_id)`: Récupération du statut d'un appareil

### Exécuter les tests

```bash
pytest tests/ -v
```

### Analyse de code

```bash
make sct # Exécute pylint, black, isort, flake8, etc.
```

## Contribution

Les contributions sont les bienvenues ! Veuillez :

1. Forker le projet
2. Créer une branche pour votre fonctionnalité (`git checkout -b feature/nouvelle-fonctionnalite`)
3. Commiter vos changements (`git commit -m 'Ajout nouvelle fonctionnalité'`)
4. Pousser vers la branche (`git push origin feature/nouvelle-fonctionnalite`)
5. Ouvrir une Pull Request

## Licence

Ce projet est distribué sous la licence **GPL-3.0**. Voir le fichier [LICENSE](LICENSE) pour plus de détails.

## Contact

Auteur : Yannick LIDIE
Email : yannick@lidie.fr

---

*Documentation générée pour le projet HHC-N818OP Standalone Client*
