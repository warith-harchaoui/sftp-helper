# SFTP Helper

[🇫🇷](https://github.com/warith-harchaoui/sftp-helper/blob/main/LISEZMOI.md) · [🇬🇧](https://github.com/warith-harchaoui/sftp-helper/blob/main/README.md)

[![CI](https://github.com/warith-harchaoui/sftp-helper/actions/workflows/ci.yml/badge.svg)](https://github.com/warith-harchaoui/sftp-helper/actions/workflows/ci.yml) [![PyPI](https://img.shields.io/pypi/v/sftp-helper.svg)](https://pypi.org/project/sftp-helper/) [![License: BSD-3-Clause](https://img.shields.io/badge/License-BSD%203--Clause-blue.svg)](https://github.com/warith-harchaoui/sftp-helper/blob/main/LICENSE) [![Python](https://img.shields.io/badge/python-3.10%E2%80%933.13-blue.svg)](#)

`SFTP Helper` fait partie d'une collection de bibliothèques appelée `AI Helpers`, développée pour bâtir des applications d'intelligence artificielle.

Le SFTP, protocole de transfert de fichiers par SSH (_SSH File Transfer Protocol_), déplace des fichiers vers et depuis un serveur distant par le même canal chiffré qu'utilise une connexion à distance en ligne de commande (SSH). Le serveur n'exige pas de mot de passe si l'on préfère s'en passer : une paire de clés prouve qui vous êtes, de la même façon qu'une clé physique prouve qu'on a le droit d'entrer dans un bâtiment ; le serveur n'a besoin de connaître que la moitié publique de votre clé. Un pipeline d'IA qui produit des fichiers (une vidéo rendue, un modèle entraîné, un lot de transcriptions) doit généralement les transmettre ailleurs sans qu'un humain ne clique dans un gestionnaire de fichiers ; `sftp-helper` fait ce transfert depuis Python, avec les vérifications d'intégrité (transferts reprenables, hachage du contenu, écritures atomiques) dont un script tournant sans surveillance a besoin, contrairement à un humain muni d'une souris.

Cette boîte à outils nécessite :
  - un fichier `settings.yaml` pour les paramètres SFTP (ou JSON ou variables d'environnement ou `.env`)
  - que vous ayez préalablement ajouté la clé SSH de votre machine locale sur le serveur SFTP

[🌍 AI Helpers](https://harchaoui.org/warith/ai-helpers)

[![logo](https://raw.githubusercontent.com/warith-harchaoui/sftp-helper/main/assets/logo.png)](https://harchaoui.org/warith/ai-helpers)

SFTP Helper est une bibliothèque Python de fonctions utilitaires pour dialoguer avec des serveurs SFTP via le client OpenSSH `sftp` du système. La vérification de la clé d'hôte est active par défaut : `~/.ssh/known_hosts` est consulté et les hôtes inconnus sont refusés.

## La promesse

**Distant par conception.** `sftp-helper` existe pour déplacer des données vers
et depuis un serveur *distant* : il n'est donc volontairement **pas**
local-first et ne fournit **aucune interface graphique**. Pour du stockage objet
cloud (S3 / GCS / Azure / MinIO) utilisez `bucket-helper` ; pour télécharger un
média depuis une URL utilisez `youtube-helper`.

**Éprouvé en production.** Douze versions publiées, une intégration continue
verte à chaque envoi (tests unitaires et lint qui bloquent la fusion au même
titre qu'un test qui échoue) et une revue de sécurité dédiée (v3.2.1) qui a
fermé une brèche d'injection de chemin dans le constructeur de commandes
batch avant qu'elle n'atteigne un seul utilisateur. Rien ici n'est promis
sans preuve à l'appui : ces chiffres viennent directement des tags du dépôt
et de son `CHANGELOG.md`, pas d'un argument commercial.

## Documentation

[💻 Documentation](https://harchaoui.org/warith/ai-helpers/docs/sftp-helper-doc/)

[🗺️ Paysage](https://github.com/warith-harchaoui/sftp-helper/blob/main/PAYSAGE.md)

[📋 Exemples](https://github.com/warith-harchaoui/sftp-helper/blob/main/EXEMPLES.md)

## Fonctionnalités

- **Upload** d'un fichier local **ou d'un répertoire** vers le serveur. Donnez
  une adresse `sftp://host/path` explicite ou omettez-la (fichier seul) pour
  obtenir un nom **haché sur le contenu** sous `sftp_destination_path` (des
  octets identiques se dédupliquent vers le même chemin). Un répertoire passe
  par `upload_many`, qui zippe puis expédie en une seule archive (un `put` +
  un `unzip` distant) dès que le serveur accepte l'exécution, au lieu d'un
  aller-retour par fichier. Options `overwrite`/`resume`/`progress` : ignorer
  les destinations déjà présentes avec la même taille (synchronisation
  incrémentale), abandonner un transfert partiel périmé ou masquer la barre
  de progression.
- **Download** d'un fichier **ou d'un répertoire** distant vers le disque (par
  défaut le nom de base distant pour un fichier seul), accéléré par archive de
  la même façon via `download_many`, avec les mêmes options `overwrite`/
  `resume`/`progress`.
- **Delete** d'un fichier distant, **idempotent** : supprimer un fichier absent
  réussit.
- **Vérifications d'existence** pour un **fichier** distant (`remote_file_exists`)
  et un **répertoire** distant (`remote_dir_exist`).
- **Lister un répertoire distant** (`list_dir`, `recursive` en option) ou
  lister avec taille/mtime par entrée en un seul passage (`list_dir_stat`) ;
  **stat d'un seul fichier distant** (`remote_stat`).
- **Création de répertoires distants** avec la sémantique `mkdir -p`
  (`make_remote_directory`) : chaque niveau intermédiaire manquant est créé.
- **Helpers de chemin** : `normalize_path` (un seul `/` initial, pas de `/` final)
  et `strip_sftp_path` (retire le schéma `sftp://` + l'hôte).
- **Context manager `remote_tempfile`** : réserve un chemin distant aléatoire
  unique (optionnellement sous un sous-dossier, optionnellement avec une
  extension) **supprimé automatiquement à la sortie du bloc**, même si une
  exception se propage ; retourne à la fois l'adresse `sftp://` et son URL HTTPS
  publique.
- **Chargeur d'identifiants** (`credentials`) résolvant JSON / YAML / dossier /
  variables d'environnement `SFTP_*` / `.env`, avec une vue masquée
  `show-credentials`.
- **Vérification stricte de la clé d'hôte, toujours active** : OpenSSH
  `StrictHostKeyChecking=yes`, sans échappatoire ; faites confiance à une clé
  supplémentaire via l'identifiant optionnel `sftp_known_hosts`.
- **Trois surfaces, un seul comportement** : bibliothèque Python, CLI argparse
  (`sftp-helper`), jumeau CLI click (`sftp-helper-click`) et surface HTTP FastAPI.
  Voir la [section multi-surface](#exposition-multi-surface).
- Catalogue de déclencheurs dans [`TRIGGERS.md`](https://github.com/warith-harchaoui/sftp-helper/blob/main/TRIGGERS.md).

## Installation

**Prérequis** : **Python 3.10–3.13** et **git**, multiplateforme :

- 🍎 **macOS** ([Homebrew](https://brew.sh)) : `brew install python git`
- 🐧 **Ubuntu/Debian** : `sudo apt update && sudo apt install -y python3 python3-pip git`
- 🪟 **Windows** (PowerShell) : `winget install Python.Python.3.12 Git.Git`

On recommande de travailler dans un environnement Python. Si vous ne savez pas en créer un, voir [🥸 Conseils techniques](https://harchaoui.org/warith/4ml/#install).

### Depuis PyPI (recommandé)

```bash
# Utilitaires SFTP de base (bibliothèque + CLI argparse)
pip install sftp-helper

# Surfaces optionnelles
pip install "sftp-helper[cli]"       # jumeau CLI en click
pip install "sftp-helper[api]"       # surface HTTP FastAPI
```

### Depuis les sources (sans PyPI)

```bash
git clone https://github.com/warith-harchaoui/sftp-helper.git
cd sftp-helper
pip install -e .

# Surfaces optionnelles
pip install -e ".[cli]"
pip install -e ".[api]"
```

## Écrire votre fichier de configuration

Un template prêt à remplir, commenté, est committé dans [`settings.yaml.example`](https://github.com/warith-harchaoui/sftp-helper/blob/main/settings.yaml.example). Copiez-le en `settings.yaml` et éditez-le sur place : le vrai `settings.yaml` est gitignored, donc pas de secret committé par accident.

```bash
cp settings.yaml.example settings.yaml
# puis éditez settings.yaml avec vos identifiants
```

Vous pouvez aussi fournir un fichier JSON, des variables d'environnement ou un fichier `.env` : `sftp-helper` essaie dans cet ordre via `os_helper.get_config`.

Seuls **trois** champs sont requis : `sftp_host`, `sftp_login`, `sftp_https`.
Authentifiez-vous par **clé SSH** (recommandé : sans mot de passe) en pointant
`sftp_key` vers votre clé **publique** (`~/.ssh/id_ed25519.pub`) ; OpenSSH
laisse votre agent SSH / jeton matériel réaliser la signature, donc aucune
matière de clé privée n'est jamais nommée dans ce fichier. Vous pouvez aussi charger
votre clé dans l'agent SSH et laisser `sftp_key` vide.
`sftp_destination_path` est optionnel et vaut par défaut la racine du serveur `/`.

_YAML_ (`settings.yaml`)
```yaml
sftp_host: "<sftp_host>"
sftp_login: "<sftp_login>"
sftp_https: "<sftp_https>"
sftp_key: "~/.ssh/id_ed25519.pub" # clé publique optionnelle ; vide -> agent SSH + clés par défaut
# sftp_passwd: "<sftp_passwd>"    # repli optionnel (nécessite `sshpass`)
# sftp_destination_path: "/base"  # optionnel ; vide -> racine "/"
# sftp_port: "2022"               # optionnel ; défaut 22
```
ou

_JSON_
```json
{
    "sftp_host": "<sftp_host>",
    "sftp_login": "<sftp_login>",
    "sftp_https": "<sftp_https>",
    "sftp_key": "~/.ssh/id_ed25519.pub"
}
```
ou

_VARIABLES D'ENVIRONNEMENT_
```bash
SFTP_HOST="<sftp_host>" \
SFTP_LOGIN="<sftp_login>" \
SFTP_HTTPS="<sftp_https>" \
SFTP_KEY="~/.ssh/id_ed25519.pub" \
python <votre_script_python>
```
ou

_.env_
```
SFTP_HOST                = <sftp_host>
SFTP_LOGIN               = <sftp_login>
SFTP_HTTPS               = <sftp_https>
SFTP_KEY                 = ~/.ssh/id_ed25519.pub
```

Où trouver ces informations (dans votre outil FTP préféré, le mien c'est FileZilla) :
  + `<sftp_host>` : l'hôte du serveur, type `sftp.example.com`
  + `<sftp_login>` : votre identifiant
  + `<sftp_https>` : l'URL web correspondant à `sftp_destination_path`
  + `sftp_key` : pointe vers la moitié **publique** de la clé que vous utilisez
    déjà pour `ssh`/`sftp` sur ce serveur (cette même clé publique doit être
    installée dans `authorized_keys` du serveur et la clé privée chargée dans
    votre agent SSH) ; ou laissez vide et reposez-vous sur votre agent SSH.
    Uniquement si vous n'utilisez pas d'agent, pointez plutôt vers la clé privée
    (`~/.ssh/id_ed25519`)
  + `<votre_script_python>` : votre script Python :)

### Pas encore de clé SSH ?

La commande `ssh-keygen` est identique sur tous les OS : elle écrit la clé
privée dans `~/.ssh/id_ed25519` et la clé publique dans `~/.ssh/id_ed25519.pub` :

```bash
ssh-keygen -t ed25519 -C "vous@example.com"
```

Chargez la clé **privée** dans votre agent SSH pour que la clé publique puisse
signer, puis installez la clé **publique** sur le serveur :

```bash
# Charger la clé privée dans l'agent
ssh-add --apple-use-keychain ~/.ssh/id_ed25519          # macOS
eval "$(ssh-agent -s)" && ssh-add ~/.ssh/id_ed25519     # Ubuntu / Linux
Start-Service ssh-agent; ssh-add $HOME\.ssh\id_ed25519  # Windows (PowerShell)

# Installer la clé publique sur le serveur (~/.ssh/authorized_keys)
ssh-copy-id -i ~/.ssh/id_ed25519.pub votre-login@sftp.example.com   # macOS / Ubuntu
type $HOME\.ssh\id_ed25519.pub | ssh votre-login@sftp.example.com "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"  # Windows
```

## Utilisation

Voici un exemple d'utilisation de SFTP Helper (**ne fonctionnera pas sans un `path/to/settings.yaml` valide**) :

```python
import sftp_helper as sftph
import os_helper as osh

# Écrire un petit fichier texte
local_file = "example.txt"
with open(local_file, "wt") as f:
    f.write("Un petit exemple de texte")

# Charger les identifiants depuis JSON / YAML ou repli sur .env / variables d'environnement.
cred = sftph.credentials("path/to/settings.yaml")

remote_file = cred["sftp_destination_path"] + "/" + local_file
url = cred["sftp_https"] + "/" + local_file

# upload() lève une exception en cas d'échec et retourne l'URL en cas de succès.
sftph.upload(local_file, cred, remote_file)
print(f"Uploadé {local_file} vers {remote_file}")
# Uploadé example.txt vers /remote/base/path/example.txt

assert osh.is_working_url(url), f"URL inaccessible : {url}"
print(f"URL en ligne : {url}")
# URL en ligne : https://files.example.com/example.txt
```

## Fichiers distants temporaires

Si vous avez besoin d'un chemin distant unique nettoyé automatiquement, utilisez le context manager `remote_tempfile` :

```python
import sftp_helper as sftph
import os_helper as osh

credentials = sftph.credentials("path/to/settings.yaml")

with sftph.remote_tempfile(credentials, ext="txt") as (sftp_address, url):
    sftph.upload("local.txt", credentials, sftp_address)
    assert osh.is_working_url(url)
# À la sortie, le fichier distant est supprimé.
```

## Vérification de la clé d'hôte

La clé d'hôte d'un serveur, c'est ce qui permet à votre machine de le reconnaître : à la première connexion, OpenSSH enregistre cette clé dans `~/.ssh/known_hosts` et chaque connexion suivante vérifie qu'elle correspond toujours. Sans cette vérification, quelqu'un capable d'intercepter votre trafic réseau pourrait se faire passer pour le serveur et lire tout ce que vous envoyez ou recevez ; la vérification fait échouer cette attaque au lieu de la laisser réussir en silence. `sftp_helper` ne désactive jamais la vérification de la clé d'hôte. Chaque appel `sftp` passe `StrictHostKeyChecking=yes` et `~/.ssh/known_hosts` est consulté automatiquement, si bien qu'un hôte dont la clé n'a pas déjà été acceptée est refusé. Pour faire confiance à un serveur dont la clé n'est pas à l'emplacement par défaut, pointez sur un fichier `known_hosts` additionnel via l'identifiant optionnel `sftp_known_hosts`.

## Exposition multi-surface

`sftp-helper` n'est pas qu'une bibliothèque : les mêmes fonctions sont
exposées comme CLI, comme surface HTTP FastAPI et comme outils MCP :

```bash
# Bibliothèque Python (par défaut)
import sftp_helper as sftph

# CLI argparse (installé automatiquement)
sftp-helper upload      --config settings.yaml --input local.txt --remote /uploads/local.txt
sftp-helper upload      --config settings.yaml --input ./local_dir --remote /uploads/dir
sftp-helper download    --config settings.yaml --remote /uploads/local.txt --output out.txt
sftp-helper exists      --config settings.yaml --remote /uploads/local.txt
sftp-helper list        --config settings.yaml --remote /uploads --recursive
sftp-helper remote-stat --config settings.yaml --remote /uploads/local.txt
sftp-helper mkdir       --config settings.yaml --remote /uploads/a/b/c

# Jumeau CLI en click (extra [cli] nécessaire)
pip install "sftp-helper[cli]"
sftp-helper-click upload --config settings.yaml --input local.txt --remote /uploads/local.txt

# Surface HTTP FastAPI (extra [api] nécessaire)
pip install "sftp-helper[api]"
SFTP_HELPER_CONFIG=./settings.yaml uvicorn sftp_helper.api:app --port 8000
# → docs OpenAPI sur http://localhost:8000/docs

# Outils MCP pour tout hôte agentique compatible (extra [mcp] nécessaire),
# la même app avec un endpoint /mcp en plus
pip install "sftp-helper[mcp]"
SFTP_HELPER_CONFIG=./settings.yaml sftp-helper-mcp
```

Image Docker (HTTP sur le port 8000) :

```bash
docker build -t sftp-helper .
docker run --rm -p 8000:8000 \
  -v $PWD/settings.yaml:/app/settings.yaml:ro \
  -e SFTP_HELPER_CONFIG=/app/settings.yaml \
  sftp-helper
```

Voir [`TRIGGERS.md`](https://github.com/warith-harchaoui/sftp-helper/blob/main/TRIGGERS.md) pour le catalogue exhaustif des formulations,
commandes et fonctions qui l'invoquent (et des cas où préférer `bucket-helper` /
`youtube-helper`).

Il n'y a **aucune interface graphique**. Un *plan de conception* de tableau de
bord (dashboard pipeline, panneau de santé du stockage, flux de transferts live)
vit dans [GUI.md](https://github.com/warith-harchaoui/sftp-helper/blob/main/GUI.md), mais aucun code de ce type n'est livré aujourd'hui.

## Auteur

 - [Warith HARCHAOUI](https://linkedin.com/in/warith-harchaoui)

## Remerciements

Remerciements chaleureux à [Mohamed Chelali](https://mchelali.github.io) et [Bachir Zerroug](https://www.linkedin.com/in/bachirzerroug) pour nos échanges fructueux.

## Licence

Ce projet est distribué sous licence BSD-3-Clause ; voir le fichier [LICENSE](https://github.com/warith-harchaoui/sftp-helper/blob/main/LICENSE) pour les détails.
