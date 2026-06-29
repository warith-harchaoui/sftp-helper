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

## Installer le paquet

Nous recommandons l'utilisation d'environnements Python. Consultez ce lien si vous ne savez pas comment faire :

[🥸 Conseils techniques](https://harchaoui.org/warith/4ml/#install)

```bash
pip install --force-reinstall --no-cache-dir git+https://github.com/warith-harchaoui/sftp-helper.git@v2.1.0
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

# Auteur
 - [Warith HARCHAOUI](https://linkedin.com/in/warith-harchaoui)

# Remerciements
Special thanks to [Mohamed Chelali](https://mchelali.github.io) and [Bachir Zerroug](https://www.linkedin.com/in/bachirzerroug) for fruitful discussions.
