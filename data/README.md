# Données

Le fichier brut **n'est pas versionné** ni inclus dans l'archive de remise :
il est téléchargé et vérifié automatiquement par `run.sh`.

## Fichier attendu

```text
data/raw/PDG000000073.1314.metadata.tsv
```

- Taille : **164 176 554 octets** (164,2 Mo)
- SHA-256 : `3170dd18b781eebfef1e83cdbbecbc5083240463938f424a31de96b922ebcb82`
- Source : NCBI Pathogen Detection, snapshot `PDG000000073.1314`
- URL : https://ftp.ncbi.nlm.nih.gov/pathogen/Results/Staphylococcus_aureus/PDG000000073.1314/Metadata/PDG000000073.1314.metadata.tsv

## Téléchargement

```bash
./run.sh          # télécharge si absent
./run.sh -f       # force le téléchargement
./run.sh -n       # mode hors ligne (fichier déjà présent)
```

## Vérification manuelle

```bash
cd data/raw
sha256sum -c ../checksums.sha256
```

## Fichier filtré

`data/processed/saureus_filtered.tsv` est produit par le pipeline Shell
(`cut | awk | sed`). Il contient 11 colonnes et 175 586 isolats. Il est
régénéré à chaque exécution et n'est pas versionné.

Voir `SOURCES.md` pour la description complète de la source.
