# Exemples SFTP Helper

🇫🇷 Français · [🇬🇧 EXAMPLES.md](https://github.com/warith-harchaoui/sftp-helper/blob/main/EXAMPLES.md)

Recettes pratiques pour `sftp-helper`, chacune étant un scénario plutôt
qu'une liste de fonctions. Tout ce qui suit [Mise en place](#mise-en-place)
suppose les imports puis le dictionnaire `cred` que cette section établit.

---

## Table des matières

[Mise en place](#mise-en-place) · [Ligne de commande](#ligne-de-commande) · [Dépannage](#dépannage)

1. [Charger les identifiants](#1-charger-les-identifiants)
2. [Envoi / téléchargement / suppression](#2-envoi--téléchargement--suppression)
3. [Vérifications d'existence](#3-vérifications-dexistence)
4. [Créer des répertoires distants](#4-créer-des-répertoires-distants)
5. [Fichiers distants temporaires (nettoyage automatique)](#5-fichiers-distants-temporaires-nettoyage-automatique)
6. [Lister et interroger](#6-lister-et-interroger)
7. [Helpers de chemin (sans serveur)](#7-helpers-de-chemin-sans-serveur)
8. [Vérification stricte de la clé d'hôte](#8-vérification-stricte-de-la-clé-dhôte)
9. [Combiner avec bucket-helper / os-helper](#9-combiner-avec-bucket-helper--os-helper)

---

## Mise en place

Installation depuis PyPI :

```bash
pip install --force-reinstall --no-cache-dir \
    sftp-helper
```

`sftp-helper` pilote le client OpenSSH `sftp` du système. Il est présent de
base sur macOS, la plupart des distributions Linux et Windows 10 1809+ /
Server 2019+ ; si `sftp` n'est pas dans votre `PATH`, installez le paquet
`openssh-client` de votre plateforme (sur Windows, activez la fonctionnalité
optionnelle « OpenSSH Client »).

Chaque extrait ci-dessous part de ces deux imports :

```python
import sftp_helper as sftph
import os_helper as osh
```

et, sauf au [§7](#7-helpers-de-chemin-sans-serveur), d'un dictionnaire `cred`
construit au [§1](#1-charger-les-identifiants) — ainsi chaque section se lit
seule, sans avoir à chercher à quoi `sftph` puis `cred` étaient liés.

## 1. Charger les identifiants

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

## 2. Envoi / téléchargement / suppression

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

Les deux sens sont reprenables, réessayés avec un recul exponentiel puis
atomiques : un envoi atterrit dans un chemin distant temporaire, renommé sur
sa destination seulement une fois la taille conforme, tandis qu'un
téléchargement atterrit dans un fichier d'appoint `<local_path>.part`, posé
par `os.replace` seulement une fois vérifié. Un appelant ne voit donc jamais
de fichier à moitié écrit. Passez `sha256=` à `download` pour vérifier aussi
le contenu, en plus de la taille :

```python
sftph.download("/inbox/report.pdf", cred, "report.pdf", sha256="e3b0c442...")
```

`overwrite=False` transforme un second appel en synchronisation incrémentale
(on saute ce qui est déjà là avec la même taille), `resume=False` abandonne
un transfert partiel périmé au lieu de le continuer puis `progress=False`
masque la barre même sur un terminal :

```python
sftph.upload("report.pdf", cred, "/inbox/report.pdf", overwrite=False, progress=False)
```

Un **répertoire** passe par les deux mêmes appels. `sftp_address` devient
alors obligatoire — il n'y a pas de fichier unique dont hacher un nom par
défaut — et désigne le répertoire de destination :

```python
sftph.upload("./renders", cred, "/inbox/renders")  # tous les fichiers non cachés, récursivement
sftph.download("/inbox/renders", cred, "./renders_copy")
```

Oublier la destination pour un répertoire est l'erreur d'argument qui vaut
d'être connue par cœur :

```python
sftph.upload("./renders", cred, "")
# ValueError: sftp_address is required when uploading a folder (there is no
# single file to derive a content-hashed default from).
```

Pour un lot explicite avec une destination par fichier, appelez directement
`upload_many` / `download_many`. Sur un serveur qui accepte aussi l'exécution
`ssh`, ils ramassent le lot en un seul transfert `tar.gz` plus une extraction
distante, au lieu d'un aller-retour par fichier ; ailleurs ils se rabattent
sur la boucle fichier par fichier, sans rien perdre :

```python
sent = sftph.upload_many(
    [("a.png", "/inbox/img/a.png"), ("b.png", "/inbox/img/b.png")],
    cred,
)
# {"a.png": "/inbox/img/a.png", "b.png": "/inbox/img/b.png"}
```

## 3. Vérifications d'existence

```python
if sftph.remote_file_exists("/inbox/report.pdf", cred):
    print("still on the server")
    # still on the server

if sftph.remote_dir_exist("/inbox/", cred):
    print("inbox directory is ready")
    # inbox directory is ready
```

## 4. Créer des répertoires distants

`make_remote_directory(path, cred)` est récursif : il parcourt chaque
niveau intermédiaire et crée ceux qui manquent.

```python
sftph.make_remote_directory("/inbox/2026-06/raw", cred)
```

## 5. Fichiers distants temporaires (nettoyage automatique)

`remote_tempfile(...)` réserve un chemin distant aléatoire unique et le
supprime automatiquement à la sortie du bloc, même si une exception est
levée.

```python
with sftph.remote_tempfile(cred, ext="json") as (sftp_address, url):
    # Le fichier n'existe pas encore : envoyez-y le contenu.
    sftph.upload("payload.json", cred, sftp_address)

    # Transmettez l'URL à un consommateur en aval (webhook, transcodeur, ...).
    assert osh.is_working_url(url), f"URL not live: {url}"
    print(f"prêt pour le consommateur en aval : {url}")
# À ce stade, le fichier distant a disparu.
```

Utilisez l'argument `subdir="..."` pour cantonner la réservation à un
sous-dossier de `cred["sftp_destination_path"]` :

```python
with sftph.remote_tempfile(cred, ext="mp4", subdir="renders/2026") as (addr, url):
    sftph.upload("clip.mp4", cred, addr)
    print(f"à mettre en file de transcodage : {url}")
```

## 6. Lister et interroger

Avant de décider quoi transférer, demandez au serveur ce qu'il détient déjà.
`list_dir` renvoie les entrées immédiates — ou les chemins relatifs de tout
l'arbre avec `recursive=True` :

```python
sftph.list_dir("/inbox", cred)
# ['2026-06', 'readme.txt']

sftph.list_dir("/inbox", cred, recursive=True)
# ['readme.txt', '2026-06/report.pdf']
```

`remote_stat` donne la taille puis la date de modification d'un fichier, ou
`None` quand le chemin est absent (ou qu'il s'agit d'un répertoire : c'est un
stat de fichier) :

```python
info = sftph.remote_stat("/inbox/readme.txt", cred)
if info is not None:
    print(info["size"], info["mtime"].isoformat())
```

`mtime` est analysé depuis la ligne `ls -l` du serveur : résolution à la
minute, aucun fuseau horaire. De quoi répondre à « ma copie locale est-elle
plus récente », pas à ce qui exige la seconde.

`list_dir_stat` en est la forme en gros : un seul parcours, une seule carte
`{chemin_relatif: {"size", "mtime"}}` pour tout l'arbre, de sorte qu'une
décision de synchronisation ne coûte aucun aller-retour par fichier :

```python
remote = sftph.list_dir_stat("/inbox", cred)
vides = [path for path, meta in remote.items() if meta["size"] == 0]
```

## 7. Helpers de chemin (sans serveur)

`normalize_path` puis `strip_sftp_path` sont des fonctions pures : aucune
connexion nécessaire, ce sont donc les extraits exécutables dès
l'installation. `normalize_path` donne à un chemin distant sa forme
canonique — un seul `/` initial, aucun final :

```python
>>> sftph.normalize_path("uploads/reports///")
'/uploads/reports'
```

`strip_sftp_path` est l'inverse de l'écriture d'une adresse complète : il
retire le schéma puis l'hôte, ne lisant que `cred["sftp_host"]` ; il est
idempotent sur un chemin déjà nu :

```python
>>> sftph.strip_sftp_path("sftp://sftp.example.com/inbox/report.pdf",
...                       {"sftp_host": "sftp.example.com"})
'/inbox/report.pdf'
```

`normalize_path` est aussi le garde-fou anti-injection du paquet. Toute
fonction acceptant un chemin distant y passe : il refuse un chemin capable
de s'échapper de la citation d'une commande batch `sftp -b` :

```python
>>> sftph.normalize_path('/inbox/"; rm -rf /')
Traceback (most recent call last):
ValueError: Unsafe remote path (contains a newline, NUL byte, or double quote, any of which could break out of an sftp/ssh command string): '/inbox/"; rm -rf /'
```

## 8. Vérification stricte de la clé d'hôte

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

Ce magasin s'*ajoute* aux magasins par défaut au lieu de les remplacer : les
hôtes auxquels vous faites déjà confiance continuent de fonctionner.

Si vous vous connectez à un hôte dont la clé n'est présente dans aucun
magasin consulté, la connexion `sftp` est refusée et l'opération lève une
exception. Il n'existe aucune option de contournement : c'est un choix de
conception.

## 9. Combiner avec bucket-helper / os-helper

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

## Ligne de commande

Une seule CLI click, `sftp-helper`, avec douze sous-commandes. Toutes celles
qui touchent au serveur acceptent `--config` (un fichier JSON/YAML ou un
répertoire qui en contient un ; omettez-le pour vous rabattre sur `.env` /
les variables d'environnement `SFTP_*`) :

```bash
sftp-helper upload           --config settings.yaml --input local.txt --remote /inbox/local.txt
sftp-helper upload           --config settings.yaml --input ./renders --remote /inbox/renders
sftp-helper download         --config settings.yaml --remote /inbox/local.txt --output out.txt
sftp-helper delete           --config settings.yaml --remote /inbox/local.txt
sftp-helper exists           --config settings.yaml --remote /inbox/local.txt
sftp-helper dir-exists       --config settings.yaml --remote /inbox
sftp-helper list             --config settings.yaml --remote /inbox --recursive
sftp-helper remote-stat      --config settings.yaml --remote /inbox/local.txt
sftp-helper mkdir            --config settings.yaml --remote /inbox/a/b/c
sftp-helper strip-path       --config settings.yaml --address sftp://sftp.example.com/inbox/local.txt
sftp-helper tempfile         --config settings.yaml --ext json --subdir renders/2026
sftp-helper show-credentials --config settings.yaml
sftp-helper normalize-path   --path "uploads/reports///"
```

`normalize-path` est la seule sous-commande qui n'a besoin ni de serveur ni
de configuration : c'est le moyen le plus rapide de prouver qu'une
installation fonctionne.

```console
$ sftp-helper normalize-path --path "uploads/reports///"
/uploads/reports
```

`upload` puis `download` acceptent aussi `--no-overwrite` (sauter les
destinations déjà présentes avec la même taille), `--no-resume` (abandonner
un transfert partiel périmé au lieu de le continuer) et `--no-progress`.

Les codes de sortie portent la réponse quand il y en a une à porter :
`exists` puis `dir-exists` affichent `true` et sortent en 0 ; sinon ils
affichent `false` et sortent en 1. `remote-stat` affiche du JSON ; sinon
`null` puis une sortie en 1 quand le chemin est absent. Un `if` de shell n'a donc rien à analyser :

```bash
if sftp-helper exists --config settings.yaml --remote /inbox/local.txt; then
    sftp-helper download --config settings.yaml --remote /inbox/local.txt
fi
```

`show-credentials` affiche la configuration résolue en JSON, `sftp_passwd`
remplacé par `***`. `-h` / `--help` fonctionne sur le groupe comme sur chaque
sous-commande ; `-V` / `--version` affiche la version installée.

## Dépannage

**`The OpenSSH 'sftp' client was not found on PATH.`** — `sftp-helper` pilote
le client du système plutôt qu'une bibliothèque SSH en processus : le binaire
lui est donc nécessaire. Le message nomme la commande d'installation de votre
OS (`apt` / `dnf` / `pacman` sous Linux, Homebrew sous macOS, la
fonctionnalité optionnelle « OpenSSH Client » sous Windows). La vérification
a lieu d'emblée, avant toute tentative de connexion.

**`Missing required keys for 'SFTP' configuration in files, .env files, or
environment variables.`** — trois clés seulement sont requises : `sftp_host`,
`sftp_login`, `sftp_https`. Passez explicitement `--config` /
`credentials(chemin)` ; sinon exportez `SFTP_HOST` / `SFTP_LOGIN` /
`SFTP_HTTPS`. Lancez `sftp-helper show-credentials` pour voir exactement ce
qui a été résolu, mot de passe masqué.

**`Host key verification failed`** — c'est attendu, pas un défaut à
contourner : `StrictHostKeyChecking=yes` est passé à chaque invocation puis
aucune option ne le désactive. Enregistrez d'abord la clé du serveur, de la
manière ordinaire :

```bash
ssh your-login@sftp.example.com    # accepter l'empreinte une fois, interactivement
# ou, sans interaction :
ssh-keyscan -t ed25519 sftp.example.com >> ~/.ssh/known_hosts
```

Si la clé doit vivre ailleurs, renseignez `sftp_known_hosts` — voir le
[§8](#8-vérification-stricte-de-la-clé-dhôte).

**`sftp_passwd is set but the 'sshpass' helper is not installed.`** — OpenSSH
refuse de lire un mot de passe depuis la ligne de commande : l'authentification
par mot de passe réclame donc la cale `sshpass`, qui n'a aucun build Windows
natif. Le remède valable partout est d'abandonner le mot de passe :
renseignez `sftp_key` (ou chargez votre clé dans l'agent SSH) puis laissez
`sftp_passwd` vide.

**Un transfert qui se bloque** — `ConnectTimeout=30` ne borne que le fait
d'*atteindre* l'hôte ; une session qui s'établit puis se tait est bornée par
`ServerAliveInterval=15` avec `ServerAliveCountMax=4`, soit environ une
minute. Les deux sont ajustables ; le multiplexage de connexion rend cela
plus important que dans un client ponctuel : une connexion maîtresse coincée
bloque tout appel ultérieur qui s'attache à sa socket de contrôle.

```bash
export SFTP_HELPER_SERVER_ALIVE_INTERVAL=30   # secondes ; 0 désactive les keepalives
export SFTP_HELPER_SERVER_ALIVE_COUNT_MAX=4   # sondes sans réponse avant abandon
```

**`ValueError: Unsafe remote path ...`** — un retour chariot, un saut de
ligne, un octet NUL ou un guillemet double dans un chemin distant est refusé
plutôt que cité, parce que chacun d'eux peut s'échapper d'une commande batch
`sftp -b`. Voir le [§7](#7-helpers-de-chemin-sans-serveur).

**Un envoi qui a échoué puis laissé quelque chose** — c'est volontaire. Le
transfert partiel reste à un chemin distant temporaire terminé par
`.sftp-helper-upload`, de sorte que le prochain `upload` vers la même
destination reprend au lieu de repartir de zéro. Passez `resume=False` (ou
`--no-resume`) pour le jeter.
