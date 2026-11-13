# SOURCES — jeu de données et références

## 1. Jeu de données principal

| Champ | Valeur |
|---|---|
| **Nom** | NCBI Pathogen Detection — *Staphylococcus aureus* |
| **Identifiant du snapshot** | `PDG000000073.1314` |
| **Fichier utilisé** | `PDG000000073.1314.metadata.tsv` |
| **URL du fichier** | https://ftp.ncbi.nlm.nih.gov/pathogen/Results/Staphylococcus_aureus/PDG000000073.1314/Metadata/PDG000000073.1314.metadata.tsv |
| **Répertoire du snapshot** | https://ftp.ncbi.nlm.nih.gov/pathogen/Results/Staphylococcus_aureus/PDG000000073.1314/ |
| **Date de téléchargement** | 30 octobre 2026 |
| **Dernière modification serveur** | 23 octobre 2026 (en-tête HTTP `Last-Modified`) |
| **Taille exacte** | 164 176 554 octets (164,2 Mo) |
| **SHA-256** | `3170dd18b781eebfef1e83cdbbecbc5083240463938f424a31de96b922ebcb82` |
| **MD5** | `edc880bc7cee726b798a66032dbbc062` |
| **Nombre de lignes** | 175 586 isolats (hors en-tête) |
| **Nombre de colonnes** | 67 |
| **Format** | TSV (tab-separated values), encodage UTF-8 |
| **Accès** | public, librement téléchargeable, sans authentification |
| **Données personnelles** | aucune donnée personnelle non anonymisée ; métadonnées d'isolats bactériens |

Le fichier est téléchargé automatiquement par `run.sh` et vérifié par
`sha256sum` avant toute analyse. Il n'est **pas** inclus dans l'archive de remise
(consigne du projet) ; le script le recrée.

### Vérification manuelle

```bash
cd data/raw
sha256sum -c ../checksums.sha256
# PDG000000073.1314.metadata.tsv: OK
```

### Commande de téléchargement utilisée

```bash
curl -L --fail --retry 3 \
  -o data/raw/PDG000000073.1314.metadata.tsv \
  "https://ftp.ncbi.nlm.nih.gov/pathogen/Results/Staphylococcus_aureus/PDG000000073.1314/Metadata/PDG000000073.1314.metadata.tsv"
```

## 2. Colonnes utilisées

Le pipeline sélectionne 11 colonnes parmi les 67 du fichier :

| Colonne | Usage |
|---|---|
| `#label` | identifiant unique de l'isolat |
| `collection_date` | année de collecte (analyse temporelle supplémentaire) |
| `geo_loc_name` | pays/région (description, non utilisée dans les tests) |
| `host_disease` | contexte clinique (description) |
| `isolation_source` | source d'isolement (description) |
| `number_drugs_resistant` | contrôle de cohérence |
| `number_amr_genes` | contrôle de cohérence |
| `number_core_amr_genes` | contrôle de cohérence |
| `AST_phenotypes` | phénotypes de sensibilité (S/I/R/NS) |
| `AMR_genotypes` | gènes et variants de résistance (AMRFinderPlus) |
| `AMR_genotypes_core` | gènes de résistance core (contrôle) |

Le champ `AMR_genotypes` contient des gènes et des variants, par exemple :

```text
mecA, erm(C), gyrA_S84L=POINT, parC_S80Y=POINT, tet(M)
```

Les variants sont normalisés vers le gène parent (`gyrA_S84L=POINT` → `gyrA`)
avant les tests statistiques.

## 3. Versions des outils présentes dans le snapshot

D'après la colonne `amrfinder_version` du fichier :

| Version AMRFinderPlus | Isolats |
|---|---:|
| 4.2.7 | 172 087 |
| 4.2.5 | 3 464 |
| 3.11.26 | 33 |
| 4.0.23 | 1 |

Base de référence principale : `refgene_db_version = 2026-08-07.1` (149 924
isolats). Types d'analyse : `COMBINED` (112 586) et `NUCLEOTIDE` (62 999).

## 4. Définitions utilisées dans le projet

- **SARM génotypique** : présence de `mecA` ou `mecC` dans `AMR_genotypes`.
- **SARM phénotypique** : `oxacillin = R` ou `cefoxitin = R` dans
  `AST_phenotypes`. **MSSA phénotypique** : au moins l'un des deux est `S` et
  aucun n'est `R`.
- **MDR** : résistance à au moins 3 classes d'antibiotiques, avec au moins 3
  classes testées. Le mapping des 59 antibiotiques vers 17 classes est dans
  `config/drug_classes.tsv`.
- **Variant normalisé** : `gyrA_S84L=POINT` → `gyrA` ; `mecA_L94F=POINT` →
  `mecA`.

## 5. Références bibliographiques

1. **NCBI Pathogen Detection**. *Staphylococcus aureus* snapshot
   `PDG000000073.1314`, metadata TSV, 164 176 554 octets, téléchargé le
   30/10/2026.
   https://ftp.ncbi.nlm.nih.gov/pathogen/Results/Staphylococcus_aureus/PDG000000073.1314/

2. **Feldgarden M., Brover V., Gonzalez-Escalona N., et al.** AMRFinderPlus and
   the Reference Gene Catalog facilitate examination of the genomic links among
   antimicrobial resistance, stress response, and virulence. *Scientific
   Reports* 2021;11:12728. https://doi.org/10.1038/s41598-021-91456-0

3. **Magiorakos A.P., Srinivasan A., Carey R.B., et al.** Multidrug-resistant,
   extensively drug-resistant and pandrug-resistant bacteria: an international
   expert proposal for interim standard definitions for acquired resistance.
   *Clinical Microbiology and Infection* 2012;18(3):268–281.
   https://doi.org/10.1111/j.1469-0691.2011.03570.x

4. **CLSI**. Performance Standards for Antimicrobial Susceptibility Testing,
   34th edition, M100. Clinical and Laboratory Standards Institute, 2024.

5. **Hanssen A.M., Ericson Sollid J.U.** SCCmec in staphylococci: genes on the
   move. *FEMS Immunology and Medical Microbiology* 2006;46(1):8–20.
   https://doi.org/10.1111/j.1574-695X.2005.00009.x

6. **Benjamini Y., Hochberg Y.** Controlling the false discovery rate: a
   practical and powerful approach to multiple testing. *Journal of the Royal
   Statistical Society B* 1995;57(1):289–300.

## 6. Conformité aux contraintes du projet

| Contrainte | Statut |
|---|---|
| Données publiques et librement téléchargeables | oui (NCBI FTP) |
| Taille entre 100 Mo et 1 Go | oui (164,2 Mo) |
| Pas de données personnelles non anonymisées | oui (métadonnées bactériennes) |
| Pas de jeu à accès contrôlé | oui (accès FTP public) |
| Pas de séquences brutes | oui (métadonnées uniquement) |
| Pas de R | oui (Shell + Python) |
| Un sujet et un jeu par groupe | oui (validé) |

## 7. Limites de la source

- La couverture AST est faible : 1 530 isolats sur 175 586 (0,87 %).
- Les phénotypes proviennent de laboratoires différents ; les panels et seuils
  peuvent varier.
- Les génotypes sont issus d'AMRFinderPlus et de versions de base hétérogènes.
- Le snapshot est une photographie datée : les identifiants et les chiffres
  peuvent évoluer dans les versions suivantes.
- Les associations observées ne sont pas ajustées sur le lignage clonal.
