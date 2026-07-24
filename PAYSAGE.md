# Paysage

🇫🇷 Français · [🇬🇧 LANDSCAPE.md](https://github.com/warith-harchaoui/sftp-helper/blob/main/LANDSCAPE.md)

Bibliothèques Python voisines et concurrentes dans l'espace « dialoguer
avec un serveur SFTP », comparées à `sftp-helper`. Les notes vont de
⭐ (1) à ⭐⭐⭐⭐⭐ (5), évaluées sur la tâche visée par `sftp-helper` —
la gestion SFTP au quotidien pour les pipelines d'IA (upload, download,
existence, mkdir -p, fichiers distants temporaires à nettoyage
automatique, vérification stricte de la clé d'hôte). Une bibliothèque
optimisée pour un tout autre usage (par ex. l'orchestration de
transferts à grande échelle en entreprise, les clients graphiques)
n'est pas pénalisée — la note reflète seulement l'adéquation à *ce*
créneau. `sftp-helper` est délibérément un outil **distant** : il
dialogue avec un serveur SSH/SFTP en direct, il n'y a donc pas de mode
local à évaluer ici.

## En un coup d'œil

| Transfert SFTP | Vérification stricte de la clé d'hôte | Ergonomie pipelines d'IA | Fichier distant temporaire à nettoyage auto | Multi-surface | Chargeur de config | État de maintenance | Installation légère |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **sftp-helper** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| paramiko | ⭐⭐ | ⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| pysftp | ⭐⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐ |
| Fabric | ⭐⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| asyncssh | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| smart-open | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| PyFilesystem2 | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| lftp | ⭐⭐⭐ | ⭐ | ⭐⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Rclone | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |

## Carte de positionnement

Représentation 2D du tableau ci-dessus.

![Carte de positionnement](https://raw.githubusercontent.com/warith-harchaoui/sftp-helper/main/assets/paysage.png)

La carte est un résumé en 2D des 7 critères : à lire comme une forme, pas comme un classement. « sftp-helper » se situe dans le coin en haut à droite. Les axes se lisent **Horizontal — Ergonomie ↔ Maintenance** et **Vertical — Installation ↔ Surface**.

## Positionnement

`sftp-helper` se place volontairement à l'intersection d'une **ergonomie
de niveau `pysftp`** (upload / download / existence / mkdir en une
ligne) et d'une **hygiène moderne de la chaîne d'approvisionnement**
(vérification stricte de la clé d'hôte sans option de contournement,
découverte des identifiants via `os-helper`, exposition multi-surface).
Il ne cherche délibérément *pas* à concurrencer `Fabric` sur
l'orchestration de tâches ni `Rclone` sur la réplication multi-backend,
et il garde `paramiko` comme seule dépendance obligatoire — on ne paie
les surfaces FastAPI / MCP / click que si on installe leurs extras. Ce
compromis est le principal différenciateur face à `pysftp` (non
maintenu depuis 2016, sans les correctifs de sécurité récents) et face
à `paramiko` brut (correct, mais qui demande 40 lignes de code avant de
pouvoir faire un `.put()`).

Quelques précisions derrière les notes. Sur la **vérification de la clé
d'hôte**, `sftp-helper` obtient le maximum car il applique par défaut
`RejectPolicy` sans option de contournement ; `paramiko` et `pysftp` ne
vérifient que si on le câble soi-même, tandis qu'`asyncssh` et `Rclone`
vérifient par défaut. Sur le **fichier distant temporaire**, le
gestionnaire de contexte `remote_tempfile` de `sftp-helper` est la seule
implémentation de première classe à nettoyage automatique du domaine.
Sa note **multi-surface** reflète argparse + click + FastAPI + MCP
derrière les mêmes signatures de fonctions, et son **chargeur de config**
délègue à `os-helper` (JSON / YAML / env / .env). `Rclone` décroche une
bonne note de config grâce à son propre format et à une surface REST via
`rclone rcd`, mais en tant que binaire Go il est plus lourd à installer
et malaisé à piloter depuis Python.

## Quand choisir quoi

- **`sftp-helper`** — préparation SFTP pour les pipelines d'IA : uploads
  par lots, fichiers de travail distants temporaires, hygiène stricte de
  la clé d'hôte, surfaces CLI + HTTP + MCP en un coup.
- **`paramiko`** — vous avez besoin de primitives SSH bas niveau
  (redirection de ports, sessions interactives, algorithmes de clé sur
  mesure) et vous êtes prêt à câbler la politique de clé d'hôte
  vous-même.
- **`asyncssh`** — vous faites déjà tourner une boucle d'événements
  `asyncio` et voulez zéro copie entre les E/S SFTP et le reste de votre
  pipeline asynchrone.
- **`Fabric`** — orchestration de tâches par SSH (déploiements, scripts
  distants), pas seulement le transfert de fichiers.
- **`smart-open` / `PyFilesystem2`** — vous voulez une seule API de type
  fichier sur S3 / GCS / SFTP / disque local sans vous soucier du
  transport sous-jacent.
- **`Rclone` / `lftp`** — vous avez besoin de synchronisation /
  réplication multi-backend de qualité production, et appeler un binaire
  externe est acceptable.
