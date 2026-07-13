# SFTP Helper

[🇫🇷](LISEZMOI.md) · [🇬🇧](README.md)

[![CI](https://github.com/warith-harchaoui/sftp-helper/actions/workflows/ci.yml/badge.svg)](https://github.com/warith-harchaoui/sftp-helper/actions/workflows/ci.yml) [![License: BSD-3-Clause](https://img.shields.io/badge/License-BSD%203--Clause-blue.svg)](LICENSE) [![Python](https://img.shields.io/badge/python-3.10%E2%80%933.13-blue.svg)](#)

`SFTP Helper` fait partie d'une collection de bibliothèques appelée `AI Helpers`, développée pour bâtir des applications d'intelligence artificielle.

Cette boîte à outils nécessite :
  - un fichier `config.json` pour les paramètres SFTP (ou YAML, ou variables d'environnement, ou `.env`)
  - que vous ayez préalablement ajouté la clé SSH de votre machine locale sur le serveur SFTP

[🌍 AI Helpers](https://harchaoui.org/warith/ai-helpers)

[![logo](assets/logo.png)](https://harchaoui.org/warith/ai-helpers)

SFTP Helper est une bibliothèque Python qui fournit des fonctions utilitaires pour travailler avec des serveurs SFTP via [paramiko](https://www.paramiko.org/). La vérification de la clé d'hôte est activée par défaut — `~/.ssh/known_hosts` est chargé et les hôtes inconnus sont refusés.

# Installation

**Prérequis** — **Python 3.10–3.13** et **git**, multiplateforme :

- 🍎 **macOS** ([Homebrew](https://brew.sh)) : `brew install python git`
- 🐧 **Ubuntu/Debian** : `sudo apt update && sudo apt install -y python3 python3-pip git`
- 🪟 **Windows** (PowerShell) : `winget install Python.Python.3.12 Git.Git`

Puis installer le paquet :


## Installer le paquet

Nous recommandons l'utilisation d'environnements Python. Consultez ce lien si vous ne savez pas comment faire :

[🥸 Conseils techniques](https://harchaoui.org/warith/4ml/#install)

```bash
pip install --force-reinstall --no-cache-dir git+https://github.com/warith-harchaoui/sftp-helper.git@v2.2.2
```

Ou depuis un clone local :

```bash
pip install -e ".[dev]"
```

## Écrire votre fichier de configuration

Un template prêt-à-remplir est committé dans [`sftp_config.json.example`](sftp_config.json.example). Copiez-le en `sftp_config.json` et éditez-le sur place — les vrais `*config.json` sont gitignored donc impossible de committer des secrets par accident :

```bash
cp sftp_config.json.example sftp_config.json
# puis éditez sftp_config.json avec vos identifiants
```

Vous pouvez aussi fournir une version YAML (`sftp_config.yaml`), des variables d'environnement, ou un fichier `.env` — `sftp-helper` essaie dans cet ordre via `os_helper.get_config` :

_JSON_
```json
{
    "sftp_host": "<sftp_host>",
    "sftp_login": "<sftp_login>",
    "sftp_passwd": "<sftp_passwd>",
    "sftp_https": "<sftp_https>",
    "sftp_destination_path": "<sftp_destination_path>"
}
```
ou

_YAML_
```yaml
sftp_host: "<sftp_host>"
sftp_login: "<sftp_login>"
sftp_passwd: "<sftp_passwd>"
sftp_https: "<sftp_https>"
sftp_destination_path: "<sftp_destination_path>"
```
ou

_VARIABLES D'ENVIRONNEMENT_
```bash
SFTP_HOST="<sftp_host>" \
SFTP_LOGIN="<sftp_login>" \
SFTP_PASSWD="<sftp_passwd>" \
SFTP_HTTPS="<sftp_https>" \
SFTP_DESTINATION_PATH="<sftp_destination_path>" \
python <votre_script_python>
```
ou

_.env_
```
SFTP_HOST                = <sftp_host>
SFTP_LOGIN               = <sftp_login>
SFTP_PASSWD              = <sftp_passwd>
SFTP_HTTPS               = <sftp_https>
SFTP_DESTINATION_PATH    = <sftp_destination_path>
```

Vous trouverez ces informations dans votre outil FTP préféré (le mien c'est FileZilla) :
  + `<sftp_host>` : le chemin du serveur, type `sftp.…`
  + `<sftp_login>` et `<sftp_passwd>` : ceux que vous utilisez dans FileZilla
  + `<sftp_destination_path>` : le chemin du dossier distant
  + `<sftp_https>` : l'URL web correspondant à `<sftp_destination_path>`
  + `<votre_script_python>` : votre script Python :)

## Utilisation

Voici un exemple d'utilisation de SFTP Helper (**ne fonctionnera pas sans un `path/to/sftp_config.json` valide**) :

```python
import sftp_helper as sftph
import os_helper as osh

# Écrire un petit fichier texte
local_file = "example.txt"
with open(local_file, "wt") as f:
    f.write("Un petit exemple de texte")

# Charger les identifiants depuis JSON / YAML, ou repli sur .env / variables d'environnement.
cred = sftph.credentials("path/to/sftp_config.json")

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

credentials = sftph.credentials("path/to/sftp_config.json")

with sftph.remote_tempfile(credentials, ext="txt") as (sftp_address, url):
    sftph.upload("local.txt", credentials, sftp_address)
    assert osh.is_working_url(url)
# À la sortie, le fichier distant est supprimé.
```

## Vérification de la clé d'hôte

`sftp_helper` ne désactive jamais la vérification de la clé d'hôte. La politique par défaut est `paramiko.RejectPolicy()` et `~/.ssh/known_hosts` est chargé automatiquement. Pour faire confiance à un serveur dont la clé n'est pas à l'emplacement par défaut, pointez sur un fichier `known_hosts` additionnel via l'identifiant optionnel `sftp_known_hosts`.

# Exposition multi-surface

`sftp-helper` n'est pas qu'une bibliothèque — les mêmes fonctions sont
exposées comme CLI, comme surface HTTP FastAPI, et comme outils MCP :

```bash
# Bibliothèque Python (par défaut)
import sftp_helper as sftph

# CLI argparse (installé automatiquement)
sftp-helper upload   --config sftp_config.json --input local.txt --remote /uploads/local.txt
sftp-helper download --config sftp_config.json --remote /uploads/local.txt --output out.txt
sftp-helper exists   --config sftp_config.json --remote /uploads/local.txt
sftp-helper mkdir    --config sftp_config.json --remote /uploads/a/b/c

# Jumeau CLI en click (extra [cli] nécessaire)
pip install 'sftp-helper[cli] @ git+https://github.com/warith-harchaoui/sftp-helper.git@v2.2.2'
sftp-helper-click upload --config sftp_config.json --input local.txt --remote /uploads/local.txt

# Surface HTTP FastAPI (extra [api] nécessaire)
pip install 'sftp-helper[api] @ git+https://github.com/warith-harchaoui/sftp-helper.git@v2.2.2'
SFTP_HELPER_CONFIG=./sftp_config.json uvicorn sftp_helper.api:app --port 8000
# → docs OpenAPI sur http://localhost:8000/docs

# Outils MCP au-dessus de FastAPI (extras [api,mcp] nécessaires)
pip install 'sftp-helper[api,mcp] @ git+https://github.com/warith-harchaoui/sftp-helper.git@v2.2.2'
sftp-helper-mcp                  # sert FastAPI + MCP sur le port 8000
```

Image Docker (HTTP + MCP sur le port 8000) :

```bash
docker build -t sftp-helper .
docker run --rm -p 8000:8000 \
  -v $PWD/sftp_config.json:/app/sftp_config.json:ro \
  -e SFTP_HELPER_CONFIG=/app/sftp_config.json \
  sftp-helper
```

Un plan GUI ambitieux (tableau de bord pipeline, panneau de santé
du stockage, flux de transferts live) vit dans [GUI.md](GUI.md).

Le paysage concurrentiel (paramiko, pysftp, asyncssh, Fabric,
smart-open, PyFilesystem2, lftp, Rclone, …) est analysé dans
[LANDSCAPE.md](LANDSCAPE.md).

# Auteur
 - [Warith HARCHAOUI](https://linkedin.com/in/warith-harchaoui)

# Remerciements
Remerciements chaleureux à [Mohamed Chelali](https://mchelali.github.io) et [Bachir Zerroug](https://www.linkedin.com/in/bachirzerroug) pour nos échanges fructueux.
