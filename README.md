# Projet « Enquête sur une maladie » — SARM

**Staphylococcus aureus résistant à la méticilline (SARM) : gènes associés à la
résistance à la méticilline et à la multirésistance.**

Pipeline reproductible Shell + Python, sans R et sans séquences brutes, construit
à partir du snapshot public **NCBI Pathogen Detection PDG000000073.1314**.

- **Groupe :** Groupe SARM
- **Membres :** 5 étudiants — noms à compléter dans `config/group.env` (`NOM Prénom 1` … `NOM Prénom 5`)
- **Cours :** Module — Enquête sur une maladie, 2026-2027
- **Date de remise :** 20 novembre 2026
- **Dépôt :** voir `LIEN_GIT.txt`

---

## 1. Question posée

> Quels gènes de résistance, présents dans le champ `AMR_genotypes`, sont associés
> (i) à la résistance à la méticilline et (ii) à la multirésistance chez
> *Staphylococcus aureus* ?

Le motif recherché est explicite :

```text
P(x) = 1  si  mecA ∈ G(x)  ou  mecC ∈ G(x),  sinon 0
```

où `G(x)` est l'ensemble des gènes extraits de `AMR_genotypes` pour l'isolat `x`.
Les variants sont ramenés au gène (`gyrA_S84L=POINT` → `gyrA`). La multirésistance
(MDR) est définie par la résistance à **au moins 3 classes d'antibiotiques**, avec
**au moins 3 classes testées**.

---

## 2. Résultats en bref

| Indicateur | Valeur |
|---|---:|
| Isolats analysés | 175 586 |
| SARM génotypiques (`mecA`/`mecC`) | 97 449 (55,5 %) |
| Isolats avec phénotype AST | 1 530 (0,87 %) |
| Phénotypes oxacilline/céfoxitine interprétables | 1 320 |
| SARM / MSSA phénotypiques | 467 / 853 |
| Concordance génotype/phénotype | 98,1 % (κ = 0,96) |
| MDR chez les SARM | 247/467 (52,9 %) |
| MDR chez les MSSA | 110/853 (12,9 %) |
| Odds ratio brut SARM vs MSSA (MDR) | 7,58 |

Principaux gènes associés au SARM hors cassette SCCmec : `gyrA` (OR 23,3),
`dfrK` (17,5), `parC` (17,1), `parE` (16,6), `dfrS1` (15,4), `ileS` (12,0),
`mph(C)` (11,8), `ant(6)-Ia` (11,6), `tet(M)` (11,0).

Principaux gènes associés à la MDR chez les SARM : `erm(C)` (OR 175), `erm(A)`
(134), `ant(9)-Ia` (126), `mecI`/`bleO` (≈ 35), `aadD1` (33), `rpsJ` (20),
`mupA` (15).

Le rapport complet de 4 pages est dans **`report/rapport.pdf`**. La présentation
(13 diapositives + notes) est dans **`presentation/`**.

---

## 3. Installation et lancement rapide

### Prérequis

- **Bash** (Linux, ou **Git Bash** sous Windows)
- **Python 3.10 ou plus récent** (`python3` ou `python`)
- `curl`, `tar`, `sha256sum`, `awk`, `sed`, `cut`, `sort`, `uniq`
- Connexion Internet au premier lancement (téléchargement de 164,2 Mo)
- Facultatif : LibreOffice pour convertir les diapositives en PDF

### Windows (Git Bash)

Ouvrir Git Bash **dans le dossier extrait**, puis :

```bash
chmod +x run.sh
./run.sh -h          # vérifie que Bash trouve le script
./run.sh             # exécution complète
```

Si `python` n'est pas dans le `PATH`, indiquez l'interpréteur :

```bash
PYTHON="/c/chemin/vers/python.exe" ./run.sh
```

### Linux

```bash
cd Projet_Maladie_SARM
chmod +x run.sh
./run.sh
```

Le script crée lui-même l'environnement `.venv`, installe `requirements.txt`,
télécharge et vérifie les données, puis produit tous les livrables. Aucune
intervention manuelle n'est nécessaire.

### Durée indicative

- Premier lancement avec téléchargement : 3 à 6 minutes selon le réseau.
- Relance hors ligne (`./run.sh -n`) : environ 1 minute (analyse + tests + PDF).

---

## 4. Options de `run.sh`

```text
./run.sh [options]

  -h            Affiche l'aide et quitte (code 0).
  -f            Force le téléchargement du fichier brut.
  -n            Mode hors ligne : aucun téléchargement.
  -i FICHIER    Utilise un TSV brut alternatif.
  -k            Conserve le dossier temporaire (débogage).
```

Exemples :

```bash
./run.sh                 # pipeline complet
./run.sh -n              # relance sans réseau
./run.sh -f              # retélécharge le snapshot
./run.sh -i data/raw/mon_extrait.tsv
```

Gestion des erreurs :

- fichier absent → message clair et **code de retour 2** ;
- option inconnue → aide + **code 2** ;
- données invalides → **code 3** ;
- toute autre erreur → arrêt immédiat (`set -euo pipefail`) et **code non nul**.

---

## 5. Ce que fait le pipeline

```text
NCBI FTP
   │  curl + contrôle taille + SHA-256 + chmod 444
   ▼
data/raw/PDG000000073.1314.metadata.tsv          (non versionné)
   │  cut -f… | awk … | sed …                     (≥ 3 commandes en tube)
   ▼
data/processed/saureus_filtered.tsv              (11 colonnes, 175 586 isolats)
   │  scripts/analysis.py (argparse, pandas, scipy)
   ├── results/tables/*.csv                      (10 CSV + 1 TSV)
   ├── results/summary.json                      (chiffres consolidés)
   └── results/figures/*.png                     (6 figures)
   │  scripts/report.py
   ├── report/rapport.pdf                         (exactement 4 pages)
   │  scripts/make_slides.py
   ├── presentation/presentation.pptx             (13 diapositives + notes)
   └── presentation/presentation.pdf              (si LibreOffice disponible)
   │  sha256sum (calcul + vérification)
   ├── results/checksums.sha256
   │  tar -czf
   └── results/archive/SARM_resultats_AAAAMMJJ_HHMMSS.tar.gz
```

Le pipeline contient aussi un **second enchaînement Shell** de plus de trois
commandes qui produit `results/tables/shell_gene_counts.tsv` :

```bash
tail -n +2 … | cut -f10 | tr ',' '\n' | sed … | sort | uniq -c | sort -rn
```

---

## 6. Arborescence du dépôt

```text
Projet_Maladie_SARM/
├── run.sh                       # point d'entrée unique, exécutable
├── requirements.txt             # environnement Python reproductible
├── README.md                    # ce fichier
├── SOURCES.md                   # source, identifiant, date, checksum
├── LIEN_GIT.txt                 # URL du dépôt + hash du commit final
├── config/
│   ├── drug_classes.tsv         # 59 antibiotiques → 17 classes (MDR)
│   ├── group.env                # numéro de groupe et noms (à personnaliser)
│   └── cron_sarm.txt            # ligne cron prête à l'emploi
├── data/
│   ├── checksums.sha256         # SHA-256 attendu du fichier brut
│   ├── README.md                # données non jointes, téléchargement
│   ├── raw/                     # TSV NCBI (ignoré par Git, lecture seule)
│   └── processed/               # TSV filtré (régénéré, ignoré par Git)
├── scripts/
│   ├── analysis.py              # analyse statistique + figures (argparse)
│   ├── report.py                # rapport PDF 4 pages (ReportLab)
│   ├── make_slides.py           # présentation PPTX (python-pptx)
│   ├── make_submission.py       # archive de remise (git archive + vérifications)
│   └── tests/
│       ├── conftest.py
│       └── test_analysis.py     # 7 tests (unitaires + intégration)
├── results/
│   ├── tables/                  # 10 CSV + palmarès Shell
│   ├── figures/                 # figures principales + supplémentaire
│   ├── archive/                 # archives tar.gz datées
│   ├── checksums.sha256         # sommes de contrôle des livrables
│   └── summary.json             # chiffres consolidés
├── report/
│   └── rapport.pdf              # 4 pages maximum
├── presentation/
│   ├── presentation.pptx        # 13 diapositives avec notes
│   └── presentation.pdf         # version PDF
├── systemd/
│   ├── sarm.service             # unité oneshot
│   └── sarm.timer               # déclenchement hebdomadaire
├── logs/                        # journaux horodatés run_AAAAMMJJ_HHMMSS.log
└── tmp/                         # fichiers temporaires (nettoyés par trap)
```

Les données brutes (`data/raw/`) et l'environnement `.venv/` ne sont **pas**
versionnés ni inclus dans l'archive de remise : `run.sh` les recrée.

---

## 7. Fichiers produits

| Fichier | Contenu |
|---|---|
| `results/summary.json` | chiffres consolidés, SHA-256, versions logicielles |
| `results/checksums.sha256` | sommes de contrôle des tableaux, figures, rapport et diapositives, vérifiées par `sha256sum -c` |
| `results/tables/cohort_summary.csv` | description des sous-cohortes |
| `results/tables/phenotype_concordance.csv` | matrice de concordance, sensibilité, spécificité, κ |
| `results/tables/gene_association_*.csv` | tests de Fisher, OR, IC 95 %, q-values |
| `results/tables/top_genes_mrsa.csv` | top gènes associés au SARM |
| `results/tables/top_genes_mdr.csv` | top gènes associés à la MDR |
| `results/tables/mdr_by_class.csv` | résistance par classe d'antibiotiques |
| `results/tables/temporal_mrsa.csv` | prévalence SARM par année |
| `results/tables/shell_gene_counts.tsv` | palmarès produit par le Shell |
| `results/figures/fig00_pipeline.png` | schéma du pipeline |
| `results/figures/fig01_cohort.png` | effectifs et MDR SARM/MSSA |
| `results/figures/fig02_mrsa_genes.png` | gènes associés au SARM |
| `results/figures/fig03_cooccurrence.png` | co-occurrence des gènes |
| `results/figures/fig04_mdr_genes.png` | gènes associés à la MDR |
| `results/figures/supplementaires/fig05_temporal.png` | évolution temporelle |
| `report/rapport.pdf` | rapport demandé (4 pages) |
| `presentation/presentation.pptx` | présentation orale (13 diapositives) |
| `results/archive/*.tar.gz` | archive datée des résultats |

Les journaux (`logs/run_*.log`) et les archives datées
(`results/archive/SARM_resultats_*.tar.gz`) sont générés à chaque exécution ;
ils ne sont pas versionnés.

---

## 8. Méthode statistique

Pour chaque gène, une table 2×2 oppose sa présence/absence dans le groupe
d'intérêt (SARM ou MDR) et dans le groupe contrôle.

- **Test exact de Fisher bilatéral** (adapté aux gènes rares).
- **Odds ratio** avec correction de Haldane-Anscombe (+0,5) et **IC 95 %** sur
  l'échelle log.
- **Correction de Benjamini-Hochberg** : seuil **q < 0,05**.
- Filtres : au moins **10 isolats** porteurs et prévalence **≥ 1 %** dans au
  moins un groupe.
- Exclusion des gènes intrinsèques présents chez **plus de 95 %** des deux
  groupes (par exemple `mepA`).
- Deux analyses : SARM vs MSSA (génotype, toute la cohorte) et MDR vs non-MDR
  (phénotype, sous-cohorte AST).

Le mapping des 59 antibiotiques vers 17 classes est dans
`config/drug_classes.tsv`.

---

## 9. Tests automatiques

```bash
.venv/Scripts/python.exe -m pytest -q scripts/tests   # Windows
.venv/bin/python -m pytest -q scripts/tests           # Linux
```

Les 7 tests couvrent :

- le parsing des phénotypes AST et des gènes (normalisation des variants) ;
- la correction de Benjamini-Hochberg ;
- l'odds ratio de Haldane-Anscombe et son IC ;
- la table 2×2, les filtres et la significativité ;
- un **test d'intégration complet** : petit TSV synthétique → `analysis.py` →
  `summary.json`, CSV et figures → `report.py` → PDF ≤ 4 pages.

`run.sh` exécute ces tests à chaque lancement, avant l'analyse réelle.

---

## 10. Tâche planifiée (cron ou systemd)

### Option A — cron

Le fichier `config/cron_sarm.txt` contient une ligne prête à l'emploi :

```cron
0 3 * * 1 cd /opt/Projet_Maladie_SARM && ./run.sh -n >> logs/cron.log 2>&1
```

Installation :

```bash
crontab -e
# coller la ligne, adapter le chemin, puis :wq
crontab -l   # vérifier
```

Le pipeline est relancé chaque lundi à 03h00, sans téléchargement (`-n`), et
écrit un journal horodaté dans `logs/`.

### Option B — systemd timer

Fichiers fournis : `systemd/sarm.service` et `systemd/sarm.timer`.

```bash
sudo cp systemd/sarm.service systemd/sarm.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sarm.timer
systemctl list-timers sarm.timer
journalctl -u sarm.service -n 50
```

Adapter `WorkingDirectory`, `ExecStart` et `User` à votre machine.

---

## 11. Reproductibilité et intégrité

- **Environnement isolé** : `.venv` créé automatiquement, dépendances figées
  dans `requirements.txt` (pandas, scipy, matplotlib, seaborn, reportlab,
  pypdf, python-pptx, pytest).
- **Contrôle d'intégrité** : taille exacte `164 176 554` octets et SHA-256
  `3170dd18b781eebfef1e83cdbbecbc5083240463938f424a31de96b922ebcb82`.
- **Checksums des sorties** : `results/checksums.sha256` est calculé puis
  vérifié par `sha256sum -c` à chaque exécution (`checksum_results()`).
- **Données brutes en lecture seule** : `chmod 0444` après vérification.
- **Journaux horodatés** : `logs/run_AAAAMMJJ_HHMMSS.log`.
- **Nettoyage** : `trap` supprime le dossier temporaire à la sortie ou à
  l'interruption (`-k` permet de le conserver pour déboguer).
- **Relance** : aucun nettoyage manuel ; les sorties sont écrasées proprement.
- **Archive datée** : `results/archive/SARM_resultats_AAAAMMJJ_HHMMSS.tar.gz`.

Pour vérifier manuellement le fichier brut :

```bash
cd data/raw
sha256sum -c ../checksums.sha256
```

---

## 12. Répartition du travail

| Membre | Rôle principal | Contributions |
|---|---|---|
| **Membre 1** | Coordinateur · données | choix du sujet, fiche de validation, téléchargement NCBI, `SOURCES.md`, checksums |
| **Membre 2** | Shell · administration | `run.sh`, `getopts`, `trap`, journaux, cron/systemd, droits, archive tar |
| **Membre 3** | Python · statistiques | `analysis.py`, parsing, Fisher, BH, OR/IC, figures, `summary.json` |
| **Membre 4** | Rapport · visualisation | `report.py`, mise en page 4 pages, relecture des résultats, figures |
| **Membre 5** | Tests · présentation · Git | `test_analysis.py`, `make_slides.py`, README, dépôt Git |

---

## 13. Correspondance avec les 20 critères techniques

| # | Chapitre | Critère | Preuve dans le dépôt |
|---:|---|---|---|
| 1 | Shell | `run.sh` affiche une aide avec `-h` | `run.sh` → `usage()` |
| 2 | Shell | au moins deux options `getopts` | `-f`, `-n`, `-i`, `-k` dans `parse_args()` |
| 3 | Shell | fichier manquant → code non nul + message clair | `parse_args()` / `verify_input()` → `die … 2` |
| 4 | Shell | ≥ 3 commandes en tube sur les données | `cut \| awk \| sed` et `tail \| cut \| tr \| sed \| sort \| uniq \| sort` |
| 5 | Fichiers | arborescence décrite dans le README | section 6 |
| 6 | Fichiers | sommes de contrôle calculées et vérifiées | `data/checksums.sha256` (brut) et `results/checksums.sha256` (sorties), via `verify_input()` et `checksum_results()` |
| 7 | Fichiers | résultats archivés dans une archive datée | `archive_results()` → `results/archive/*.tar.gz` |
| 8 | Fichiers | `SOURCES.md` complet | `SOURCES.md` (ID, URL, date, taille, SHA-256) |
| 9 | Admin | environnement reproductible fourni | `requirements.txt` + `.venv` créé par `setup_venv()` |
| 10 | Admin | tâche cron ou timer fournie et documentée | `config/cron_sarm.txt`, `systemd/`, section 10 |
| 11 | Admin | journal horodaté dans `logs/` | `setup_logging()` → `logs/run_*.log` |
| 12 | Admin | scripts exécutables et données brutes en lecture seule | `chmod +x`, `chmod 0444` dans `verify_input()` |
| 13 | Script | `trap` supprime les fichiers temporaires | `cleanup()` + `trap cleanup EXIT/INT/TERM` |
| 14 | Script | arrêt à la première erreur avec message clair | `set -euo pipefail`, `die()`, `trap` |
| 15 | Script | au moins 3 fonctions réutilisées | 20 fonctions (`parse_args`, `download_data`, `verify_input`, `prepare_data`, `setup_venv`, `checksum_results`, `run_analysis`, `build_report`, …) |
| 16 | Script | relance possible sans nettoyage manuel | sorties écrasées, `-f`, `-n`, `trap` |
| 17 | Python | script appelé par `run.sh` avec `argparse` | `analysis.py`, `report.py`, `make_slides.py` |
| 18 | Python | au moins une figure produite automatiquement | 6 figures dans `results/figures/` |
| 19 | Python | résultats chiffrés en CSV ou JSON | 10 CSV + `summary.json` |
| 20 | Python | au moins un test automatique | `scripts/tests/test_analysis.py` (7 tests) |

---

## 14. Personnalisation avant remise

1. **Groupe et membres** : éditer `config/group.env`.

   ```bash
   GROUP_NAME="Groupe 07"
   GROUP_MEMBERS="NOM Prénom; NOM Prénom; …"
   ```

2. **Dépôt Git** : l'URL et le hash sont déjà renseignés dans `LIEN_GIT.txt`
   (`https://github.com/aimenmdz21/Projet_Maladie_SARM`). Après une modification,
   committer, pousser sur `main`, puis régénérer le zip : `git archive`
   substitue automatiquement le hash final.

3. **Régénérer le rapport et les diapositives** après personnalisation :

   ```bash
   ./run.sh -n
   ```

4. **Créer l'archive de remise** :

   ```bash
   python scripts/make_submission.py --output ../Projet_Maladie_Groupe_07.zip
   ```

   Le script part de `git archive HEAD`, ajoute `rapport.pdf` à la racine et
   exclut `results/`, `logs/`, `tmp/`, `data/raw/`, `data/processed/` et
   `.venv/`. Il vérifie aussi la présence des livrables, le hash du commit dans
   `LIEN_GIT.txt` et les bits exécutables. Le correcteur télécharge les données
   avec `run.sh`.

---

## 15. Dépannage

| Problème | Solution |
|---|---|
| `python: command not found` | installer Python 3.10+ ou `PYTHON=/chemin/python ./run.sh` |
| `Permission denied` sur `run.sh` | `chmod +x run.sh` (Linux/Git Bash) |
| Téléchargement interrompu | relancer `./run.sh -f` ; le `trap` nettoie le temporaire |
| `SHA-256 incorrect` | supprimer `data/raw/PDG…tsv` puis `./run.sh -f` |
| Pas de réseau | `./run.sh -n` si le fichier brut est déjà présent |
| LibreOffice absent | le PPTX est produit ; `presentation.pdf` est simplement ignoré |
| Le rapport dépasse 4 pages | `report.py` renvoie le code 3 ; réduire le contenu |
| Tests en échec | `python -m pytest -q scripts/tests` pour le détail |

---

## 16. Sources et références

Voir **`SOURCES.md`** pour l'identifiant, l'URL, la date de téléchargement, la
taille, le SHA-256 et les références bibliographiques. Les données sont
publiques, librement téléchargeables, sans données personnelles non anonymisées.

---

## 17. Licence et usage

Projet académique. Les données NCBI restent soumises aux conditions d'utilisation
de NCBI. Le code peut être réutilisé à des fins pédagogiques en citant la source
des données et le présent dépôt.
