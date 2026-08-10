# Exemples SFTP Helper

Recettes pratiques pour `sftp-helper`. Chaque extrait suppose :

```python
import sftp_helper as sftph
import os_helper as osh
```

et que vous avez écrit vos identifiants dans `path/to/settings.yaml`
(ou en YAML, en `.env` ou en variables d'environnement : voir le README
pour les clés requises).

---

## Table des matières

1. [Mise en place](#mise-en-place)
2. [Charger les identifiants](#charger-les-identifiants)
3. [Envoi / téléchargement / suppression](#envoi--téléchargement--suppression)
4. [Vérifications d'existence](#vérifications-dexistence)
5. [Créer des répertoires distants](#créer-des-répertoires-distants)
6. [Fichiers distants temporaires (nettoyage automatique)](#fichiers-distants-temporaires-nettoyage-automatique)
7. [Vérification stricte de la clé d'hôte](#vérification-stricte-de-la-clé-dhôte)
8. [Combiner avec bucket-helper / os-helper](#combiner-avec-bucket-helper--os-helper)

---

## Mise en place

Installez avec pip (épinglez la version voulue) :

```bash
pip install --force-reinstall --no-cache-dir \
    sftp-helper
```

`sftp-helper` pilote le client OpenSSH `sftp` du système. Il est présent de
base sur macOS, la plupart des distributions Linux et Windows 10 1809+ /
Server 2019+ ; si `sftp` n'est pas dans votre `PATH`, installez le paquet
`openssh-client` de votre plateforme (sur Windows, activez la fonctionnalité
optionnelle « OpenSSH Client »).

## Charger les identifiants

`credentials(...)` renvoie un dictionnaire assemblé à partir d'un fichier
JSON, YAML, `.env` ou de variables d'environnement. L'ordre de repli est
dicté par `os_helper.get_config`.

```python
# Depuis un fichier JSON / YAML
cred = sftph.credentials("path/to/settings.yaml")

# Ou repli sur .env / les variables d'environnement SFTP_*
cred = sftph.credentials()
```

Clés requises : `sftp_host`, `sftp_login`, `sftp_https`. Clés optionnelles :
`sftp_key` (chemin vers votre clé SSH, il est recommandé de fournir votre
clé **publique** `~/.ssh/id_ed25519.pub` pour que l'agent signe sans qu'aucun
secret privé ne soit nommé ici ; un chemin vers une clé privée fonctionne
aussi ; vide ⇒ agent SSH et identités par défaut de `~/.ssh`),
`sftp_passwd` (repli par mot de passe, nécessite `sshpass`),
`sftp_destination_path` (par défaut : la racine du serveur `/`),
`sftp_port` (par défaut `22`), `sftp_known_hosts` (fichier known-hosts
supplémentaire).

### Pas encore de clé SSH ?

La commande `ssh-keygen` est identique sur chaque système : elle écrit la
clé privée dans `~/.ssh/id_ed25519` et la clé publique dans
`~/.ssh/id_ed25519.pub` :

```bash
ssh-keygen -t ed25519 -C "you@example.com"
```

Chargez la clé **privée** dans votre agent SSH pour que la clé publique
puisse signer :

```bash
# macOS
ssh-add --apple-use-keychain ~/.ssh/id_ed25519
# Ubuntu / Linux
eval "$(ssh-agent -s)" && ssh-add ~/.ssh/id_ed25519
# Windows (PowerShell)
Start-Service ssh-agent; ssh-add $HOME\.ssh\id_ed25519
```

Installez la clé **publique** sur le serveur (`~/.ssh/authorized_keys`) :

```bash
# macOS / Ubuntu
ssh-copy-id -i ~/.ssh/id_ed25519.pub your-login@sftp.example.com
# Windows (PowerShell)
type $HOME\.ssh\id_ed25519.pub | ssh your-login@sftp.example.com "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
```

## Envoi / téléchargement / suppression

```python
# Envoie un fichier local. Si sftp_address est vide, sftp-helper construit
# un nom fondé sur le contenu (hash) sous cred["sftp_destination_path"].
remote_uri = sftph.upload("report.pdf", cred)
# remote_uri est la forme complète sftp:// (ou chemin distant) de la destination.

# Ou envoi vers une destination déterministe :
sftph.upload("report.pdf", cred, "/inbox/report.pdf")

# Téléchargement (par défaut, le nom de base distant dans le répertoire courant)
sftph.download("/inbox/report.pdf", cred)
sftph.download("/inbox/report.pdf", cred, "local_copy.pdf")

# Suppression : idempotente (renvoie True si le fichier distant a bien disparu après l'appel)
sftph.delete("/inbox/report.pdf", cred)
```

## Vérifications d'existence

```python
if sftph.remote_file_exists("/inbox/report.pdf", cred):
    print("still on the server")
    # still on the server

if sftph.remote_dir_exist("/inbox/", cred):
    print("inbox directory is ready")
    # inbox directory is ready
```

## Créer des répertoires distants

`make_remote_directory(path, cred)` est récursif : il parcourt chaque
niveau intermédiaire et crée ceux qui manquent.

```python
sftph.make_remote_directory("/inbox/2026-06/raw", cred)
```

## Fichiers distants temporaires (nettoyage automatique)

`remote_tempfile(...)` réserve un chemin distant aléatoire unique et le
supprime automatiquement à la sortie du bloc, même si une exception est
levée.

```python
with sftph.remote_tempfile(cred, ext="json") as (sftp_address, url):
    # Le fichier n'existe pas encore : envoyez-y le contenu.
    sftph.upload("payload.json", cred, sftp_address)

    # Transmettez l'URL à un consommateur en aval (webhook, transcodeur, ...).
    assert osh.is_working_url(url), f"URL not live: {url}"
    notify_downstream(url)
# À ce stade, le fichier distant a disparu.
```

Utilisez l'argument `subdir="..."` pour cantonner la réservation à un
sous-dossier de `cred["sftp_destination_path"]` :

```python
with sftph.remote_tempfile(cred, ext="mp4", subdir="renders/2026") as (addr, url):
    sftph.upload("clip.mp4", cred, addr)
    queue_for_transcoding(url)
```

## Vérification stricte de la clé d'hôte

`sftp-helper` ne désactive jamais la vérification de la clé d'hôte. Chaque
appel `sftp` passe `StrictHostKeyChecking=yes` et consulte automatiquement
`~/.ssh/known_hosts`. Pour faire confiance à un serveur dont la clé vit
dans un emplacement non standard, pointez vers le fichier known-hosts
supplémentaire via l'identifiant optionnel `sftp_known_hosts` :

```python
cred = sftph.credentials("path/to/settings.yaml")
cred["sftp_known_hosts"] = "/etc/ssh/known_hosts.d/inbox-prod"
sftph.upload("payload.json", cred, "/inbox/payload.json")
```

Si vous vous connectez à un hôte dont la clé n'est présente dans aucun
magasin consulté, la connexion `sftp` est refusée et l'opération lève une
exception. Il n'existe aucune option de contournement : c'est un choix de
conception.

## Combiner avec bucket-helper / os-helper

Un enchaînement courant : écrire un fichier localement, le pousser sur S3
(stockage de long terme), puis le refléter vers la boîte de réception SFTP
d'un partenaire (consommateur ponctuel) :

```python
import os_helper as osh
import bucket_helper as bh
import sftp_helper as sftph

osh.verbosity(2)

# Archive de long terme sur S3
s3_cred = bh.credentials("path/to/settings.yaml")
s3_uri = bh.upload("monthly_report.pdf", s3_cred, "reports/2026-06.pdf")

# Miroir vers le partenaire SFTP
sftp_cred = sftph.credentials("path/to/settings.yaml")
sftph.upload("monthly_report.pdf", sftp_cred, "/inbox/2026-06.pdf")

print(f"Archived at {s3_uri}; delivered to SFTP partner.")
# Archived at s3://my-bucket/reports/2026-06.pdf; delivered to SFTP partner.
```
