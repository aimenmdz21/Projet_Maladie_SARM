# Fiche de validation du sujet

**Projet « Enquête sur une maladie » — 2026-2027**

| Rubrique | Contenu |
|---|---|
| **Groupe et membres** | `Groupe SARM` — `NOM Prénom 1`, `NOM Prénom 2`, `NOM Prénom 3`, `NOM Prénom 4`, `NOM Prénom 5` |
| **Jeu de données** | NCBI Pathogen Detection — *Staphylococcus aureus*, snapshot `PDG000000073.1314`, fichier `PDG000000073.1314.metadata.tsv`, 164 176 554 octets (164,2 Mo), téléchargé le 30/10/2026. URL : https://ftp.ncbi.nlm.nih.gov/pathogen/Results/Staphylococcus_aureus/PDG000000073.1314/Metadata/PDG000000073.1314.metadata.tsv |
| **Maladie et question** | Les infections à *Staphylococcus aureus* résistant à la méticilline (SARM) sont un problème majeur de santé publique. Quels gènes de résistance sont associés (i) à la résistance à la méticilline et (ii) à la multirésistance chez *S. aureus* ? |
| **Motif** | Présence de `mecA` ou `mecC` dans `AMR_genotypes` ; validation par le phénotype oxacilline/céfoxitine R. MDR = résistance à au moins 3 classes d'antibiotiques, avec au moins 3 classes testées. |
| **Méthode** | Pipeline Shell + Python : téléchargement et SHA-256, filtrage `cut \| awk \| sed`, parsing des gènes et variants, tests exacts de Fisher, odds ratios avec correction de Haldane-Anscombe, IC 95 %, correction de Benjamini-Hochberg, figures et rapport PDF de 4 pages. |
| **Livrables** | `run.sh`, `README.md`, `SOURCES.md`, `LIEN_GIT.txt`, `rapport.pdf` (4 pages), résultats CSV/JSON, figures, tests, diapositives de présentation. |
| **Contraintes respectées** | Données publiques (NCBI FTP), 164,2 Mo (entre 100 Mo et 1 Go), aucune donnée personnelle non anonymisée, pas de séquences brutes, pas de R. |

## Résultats attendus (indicatifs)

- 175 586 isolats ; 55,5 % de SARM génotypiques.
- 1 320 phénotypes oxacilline/céfoxitine interprétables ; concordance 98,1 %.
- MDR : 52,9 % des SARM vs 12,9 % des MSSA (OR brut 7,58).
- Gènes associés au SARM : `gyrA`, `parC`, `dfrK`, `mph(C)`, `ant(6)-Ia`, `tet(M)`.
- Gènes associés à la MDR : `erm(C)`, `erm(A)`, `ant(9)-Ia`, `aadD1`, `mecI`, `bleO`.

## Validation

- [ ] Sujet validé par l'enseignant
- [ ] Groupe et membres complétés (remplacer les `NOM Prénom 1..5`)
- [x] Dépôt Git créé et URL reportée dans `LIEN_GIT.txt`
- [ ] Archive `Projet_Maladie_Groupe_XX.zip` déposée sur Google Classroom

> Remplacer « Groupe SARM » par le numéro de groupe officiel si l'enseignant en
> exige un. Le nom de l'archive suit `config/group.env` via
> `scripts/make_submission.py`.
