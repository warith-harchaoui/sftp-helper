# Paysage

🇫🇷 Français · [🇬🇧 LANDSCAPE.md](https://github.com/warith-harchaoui/sftp-helper/blob/main/LANDSCAPE.md)

Bibliothèques Python voisines et concurrentes dans l'espace « dialoguer
avec un serveur SFTP », comparées à `sftp-helper`. Les notes vont de
⭐ (1) à ⭐⭐⭐⭐⭐ (5), évaluées sur la tâche visée par `sftp-helper` :
la gestion SFTP au quotidien pour les pipelines d'IA (upload, download,
existence, mkdir -p, fichiers distants temporaires à nettoyage
automatique, vérification stricte de la clé d'hôte). Une bibliothèque
optimisée pour un tout autre usage (par ex. l'orchestration de
transferts à grande échelle en entreprise, les clients graphiques)
n'est pas pénalisée : la note reflète seulement l'adéquation à *ce*
créneau. `sftp-helper` est délibérément un outil **distant** : il
dialogue avec un serveur SSH/SFTP en direct, il n'y a donc pas de mode
local à évaluer ici.

## En un coup d'œil

<!-- TABLE:START -->
| Transfert SFTP | Vérification stricte de la clé d'hôte | Ergonomie pipelines d'IA | Fichier distant temporaire à nettoyage auto | Multi-surface | Chargeur de config | État de maintenance | Installation légère |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **sftp-helper** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| paramiko | ⭐⭐ | ⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| pysftp | ⭐⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐ |
| Fabric | ⭐⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| asyncssh | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| smart-open | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| PyFilesystem2 | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐ | ⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| lftp | ⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Rclone | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
<!-- TABLE:END -->

## Carte de positionnement

<!-- FIGURE:START -->
Représentation 2D du tableau ci-dessus.

![Carte de positionnement](https://raw.githubusercontent.com/warith-harchaoui/sftp-helper/main/assets/paysage.png)

La carte est un résumé en 2D des 7 critères : à lire comme une forme, pas comme un classement. « sftp-helper » se situe dans le coin en haut à droite. Les axes se lisent **Horizontal — Fluidité ↔ Robustesse** et **Vertical — Simplicité ↔ Adaptabilité**.
<!-- FIGURE:END -->

## Positionnement

`sftp-helper` se place volontairement à l'intersection d'une **ergonomie
de niveau `pysftp`** (upload / download / existence / mkdir en une
ligne) et d'une **hygiène moderne de la chaîne d'approvisionnement**
(vérification stricte de la clé d'hôte sans option de contournement,
découverte des identifiants via `os-helper`, exposition multi-surface).
Il ne cherche délibérément *pas* à concurrencer `Fabric` sur
l'orchestration de tâches ni `Rclone` sur la réplication multi-backend,
et il s'appuie sur le **client OpenSSH `sftp` du système**, il n'a donc
aucune dépendance SSH Python (seulement `os-helper`) et s'authentifie
exactement comme vos propres `ssh`/`sftp` (agent, `~/.ssh/config`, clés
matérielles). On ne paie les surfaces FastAPI / MCP que si on installe
leurs extras. Ce compromis est le principal différenciateur face à
`pysftp` (dont la dernière version, 0.2.9, date du 6 juillet 2016) et
face à `paramiko` brut (correct, mais il faut assembler le transport,
choisir une politique de clé d'hôte inconnue puis ouvrir un
`SFTPClient` avant le moindre `.put()`).

Quelques précisions derrière les notes. Sur la **vérification de la clé
d'hôte**, `sftp-helper` obtient le maximum car chaque invocation passe
`StrictHostKeyChecking=yes` et aucune option ne la désactive.
`asyncssh` vérifie aussi par défaut : son argument `known_hosts` se
rabat sur `~/.ssh/known_hosts` et seul un `known_hosts=None` explicite
coupe le contrôle. `paramiko` refuse un hôte inconnu par défaut
(`RejectPolicy`), mais un `SSHClient` neuf ne détient **aucune** clé
d'hôte tant que `load_system_host_keys()` n'a pas été appelé : le
magasin reste à votre charge. Le backend SFTP de `Rclone` part du
réglage inverse : il ne vérifie rien tant que `known_hosts_file` n'est
pas renseigné (ou qu'une clé n'est pas épinglée via
`--sftp-pin-host-key`) ; il avertit d'ailleurs « No host key validation
is being performed » à chaque démarrage dans ce mode. Ses quatre
étoiles saluent la mécanique puis sa documentation, pas un réglage actif
à l'arrivée.

Sur le **fichier distant temporaire**, le context manager `remote_tempfile`
de `sftp-helper` est la seule implémentation de première classe à nettoyage
automatique parmi les bibliothèques Python retenues ici ; seul le binaire
`Rclone` s'en approche. Sa note **multi-surface** reflète une CLI click, une surface HTTP
FastAPI puis les outils MCP publiés depuis cette même application, tous
derrière les mêmes signatures de fonctions ; son **chargeur de config**
délègue à `os-helper` (JSON / YAML / env / .env). `Rclone` décroche une
bonne note de config grâce à son propre format et à une surface REST via
`rclone rcd`, mais en tant que binaire Go il est plus lourd à installer
et malaisé à piloter depuis Python.

## Quand choisir quoi

- **`sftp-helper`** : préparation SFTP pour les pipelines d'IA : uploads
  par lots, fichiers de travail distants temporaires, hygiène stricte de
  la clé d'hôte, surfaces CLI + HTTP en un coup.
- **`paramiko`** : vous avez besoin de primitives SSH bas niveau
  (redirection de ports, sessions interactives, algorithmes de clé sur
  mesure) et vous êtes prêt à câbler la politique de clé d'hôte
  vous-même.
- **`asyncssh`** : vous faites déjà tourner une boucle d'événements
  `asyncio` et voulez zéro copie entre les E/S SFTP et le reste de votre
  pipeline asynchrone.
- **`Fabric`** : orchestration de tâches par SSH (déploiements, scripts
  distants), pas seulement le transfert de fichiers.
- **`smart-open` / `PyFilesystem2`** : vous voulez une seule API de type
  fichier sur S3 / GCS / SFTP / disque local sans vous soucier du
  transport sous-jacent.
- **`Rclone` / `lftp`** : vous avez besoin de synchronisation /
  réplication multi-backend de qualité production et appeler un binaire
  externe est acceptable.

## Sources et date de relevé

**Relevé du 27 octobre 2026.** Rien ici n'a été mesuré par un banc
d'essai : c'est une comparaison d'adéquation à un seul métier, les
étoiles sont des jugements. Ce qui peut se périmer, c'est la moitié
factuelle — dates de publication puis comportements documentés du
logiciel des autres — alors c'est elle que cette section fixe.

Données de publication, lues le jour dit via l'API JSON de PyPI
(`https://pypi.org/pypi/<nom>/json`) :

| Projet | Dernière version | Publiée le |
| --- | --- | --- |
| paramiko | 5.1.0 | 2026-10-18 |
| smart-open | 8.0.4 | 2026-10-17 |
| asyncssh | 2.24.1 | 2026-10-04 |
| Fabric | 3.2.3 | 2026-04-06 |
| PyFilesystem2 (`fs`) | 2.4.16 | 2022-05-02 |
| pysftp | 0.2.9 | 2016-07-06 |

`Rclone` n'est pas un paquet Python : v1.75.2, publiée le 2026-10-09,
d'après l'API des releases GitHub. `lftp` ne se distribue que par les
paquets système puis aucune date n'a été vérifiée pour lui, ce qui fait
de sa case **état de maintenance** la moins bien sourcée du tableau — à
lire comme une impression plutôt que comme une mesure.

Comportements documentés, d'après la référence de chaque projet :

- [`connect()` d'asyncssh](https://asyncssh.readthedocs.io/en/latest/api.html) —
  « If this is not specified, the keys will be looked up in the file
  .ssh/known_hosts. If this is explicitly set to `None`, server host key
  validation will be disabled. »
- [`SSHClient` de paramiko](https://docs.paramiko.org/en/latest/api/client.html) —
  `RejectPolicy` est la politique par défaut pour une clé d'hôte
  inconnue, puis une clé ne compte comme connue qu'une fois chargée par
  `load_system_host_keys()` ou `load_host_keys()`. Le détail « aucune
  clé à la construction » a été vérifié sur le paramiko 3.5.1 installé,
  pas seulement lu.
- [le backend SFTP de rclone](https://rclone.org/sftp/) — « Optional path
  to known_hosts file. Set this value to enable server host key
  validation », ainsi que l'avertissement « No host key validation is
  being performed » émis à chaque démarrage sans ce réglage.

Les affirmations propres à `sftp-helper` se vérifient dans ce dépôt
plutôt qu'en citation : `_ssh_options` dans `sftp_helper/main.py` pour le
`StrictHostKeyChecking=yes` sans échappatoire, `sftp_helper/cli.py` puis
`sftp_helper/api.py` pour les surfaces, `CHANGELOG.md` pour l'historique.

Les étoiles elles-mêmes sont générées depuis `assets/paysage.csv`, source
de vérité à la fois du tableau ci-dessus puis de la carte de
positionnement. Une bibliothèque conçue pour un autre métier
(orchestration de transferts en entreprise, client graphique,
réplication multi-backend) y obtient une note basse sans que ce soit un
défaut : voir le préambule.

## Idées à reprendre

Étudié plutôt que deviné : ce que chaque voisin fait mieux, puis ce que cette bibliothèque devrait changer pour l'égaler. Rien ici n'est un engagement : c'est la liste de lecture dont part la version suivante.

- **`pysftp` est mort, puis le tableau devrait le dire** — Dernière publication en 2016, non maintenu, puis toujours incapable d'utiliser des clés Ed25519 ou ECDSA alors que le paramiko qu'il enveloppe le sait. C'est le premier résultat que les gens trouvent puis le pire choix qu'ils puissent faire ; le nommer franchement sert plus qu'une note en étoiles.

- **`asyncssh` — rapide, puis bloqué par sa licence pour beaucoup d'appelants** — C'est la meilleure option asynchrone, mais elle est publiée sous EPL, qui ne se combine ni avec une distribution GPL ni avec une BSD. Pour une suite en BSD-3 c'est un arrêt net ; cela relève de la comparaison comme un fait de licence plutôt que de performance.

- **`sshfs` — fsspec au-dessus d'asyncssh, nettement plus rapide que paramiko** — Là où la licence le permet, l'écart de débit est assez grand pour compter sur du transfert en masse. À mesurer ici avant de supposer que la vitesse de paramiko est le plafond.

- **`Rclone` — reprendre, vérifier, puis limiter la bande passante** — Une vérification par empreinte après transfert, des envois partiels reprenables puis un plafond de débit sont les trois choses qu'un exploitant réclame la première fois qu'un transfert échoue à 90 % sur un lien partagé.
