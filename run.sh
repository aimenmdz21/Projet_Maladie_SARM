#!/usr/bin/env bash
# =============================================================================
# Projet SARM — version compacte du pipeline
# Acquisition -> contrôle -> filtrage Shell -> Python -> tests -> PDF -> archive
# =============================================================================
set -euo pipefail
export PYTHONIOENCODING="utf-8" PYTHONUTF8="1"

cd "$(dirname "$0")"

RAW_URL="https://ftp.ncbi.nlm.nih.gov/pathogen/Results/Staphylococcus_aureus/PDG000000073.1314/Metadata/PDG000000073.1314.metadata.tsv"
RAW="data/raw/PDG000000073.1314.metadata.tsv"
SUM="data/checksums.sha256"
SIZE=164176554
OUT="data/processed/saureus_filtered.tsv"

FORCE=0; OFFLINE=0; KEEP=0; INPUT=""; TMP=""; LOG=""; PY=""

usage() {
  cat <<'EOF'
Projet SARM — pipeline reproductible NCBI Pathogen Detection

Usage : ./run.sh [options]
  -h            aide
  -f            force le téléchargement
  -n            mode hors ligne
  -i FICHIER    fichier TSV alternatif
  -k            conserve le dossier temporaire

Codes : 0 succès · 1 erreur · 2 argument/fichier invalide · 3 données/rapport
EOF
}

log()  { printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
die()  { log "ERREUR : $1" >&2; exit "${2:-1}"; }

cleanup() {
  local code=$?
  if [[ -n "$TMP" && -d "$TMP" ]]; then
    if [[ "$KEEP" -eq 1 ]]; then log "Temporaire conservé : $TMP"
    else rm -rf "$TMP"; fi
  fi
  if [[ "$code" -ne 0 && -n "$LOG" ]]; then
    printf '[%s] ÉCHEC (code %s). Journal : %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$code" "$LOG" >&2
  fi
}
trap cleanup EXIT
trap 'log "Interruption."; exit 130' INT TERM

parse_args() {
  local o
  while getopts ":hfnki:" o; do
    case "$o" in
      h) usage; exit 0 ;;
      f) FORCE=1 ;;
      n) OFFLINE=1 ;;
      k) KEEP=1 ;;
      i) INPUT="$OPTARG" ;;
      :) die "L'option -$OPTARG requiert un argument." 2 ;;
      \?) die "Option inconnue : -$OPTARG." 2 ;;
    esac
  done
  shift $((OPTIND - 1))
  [[ $# -eq 0 ]] || die "Arguments en trop : $*" 2
  [[ "$FORCE" -eq 1 && "$OFFLINE" -eq 1 ]] && die "-f et -n sont incompatibles." 2
  [[ -z "$INPUT" || -f "$INPUT" ]] || die "Fichier introuvable : $INPUT" 2
}

prepare_dirs() {
  mkdir -p data/raw data/processed results/{tables,figures,archive} logs report presentation tmp
  TMP=$(mktemp -d)
}

setup_logging() {
  LOG="logs/run_$(date '+%Y%m%d_%H%M%S').log"
  exec > >(tee -a "$LOG") 2>&1
  log "Journal : $LOG"
}

download_data() {
  if [[ -n "$INPUT" ]]; then RAW="$INPUT"; log "Fichier alternatif : $RAW"; return; fi
  if [[ -f "$RAW" && "$FORCE" -eq 0 ]]; then log "Fichier présent : $RAW"; return; fi
  [[ "$OFFLINE" -eq 0 ]] || die "Mode -n : fichier absent ($RAW)." 2
  command -v curl >/dev/null || die "curl absent." 127
  if [[ -f "$RAW" ]]; then chmod u+w "$RAW" 2>/dev/null || true; fi
  log "Téléchargement du snapshot NCBI…"
  curl -L --fail --retry 3 --retry-delay 2 -o "$TMP/data.tsv" "$RAW_URL" \
    || die "Téléchargement échoué." 1
  mv "$TMP/data.tsv" "$RAW"
  chmod 0444 "$RAW" 2>/dev/null || true
}

verify_input() {
  [[ -f "$RAW" ]] || die "Fichier introuvable : $RAW" 2
  [[ -f "$SUM" ]] || die "Checksums introuvables : $SUM" 2
  local s h e
  s=$(wc -c < "$RAW" | tr -d '[:space:]')
  log "Taille : $s octets"
  if [[ -z "$INPUT" ]]; then
    [[ "$s" -eq "$SIZE" ]] || die "Taille inattendue : $s (attendu $SIZE)." 2
  fi
  e=$(awk 'NF{print $1; exit}' "$SUM")
  h=$(sha256sum "$RAW" | awk '{print $1}')
  log "SHA-256 : $h"
  if [[ -n "$INPUT" ]]; then
    log "Fichier alternatif : pas de référence."
  elif [[ "$h" == "$e" ]]; then
    log "SHA-256 conforme."
    chmod 0444 "$RAW" 2>/dev/null || true
  else
    die "SHA-256 incorrect (attendu $e)." 2
  fi
}

prepare_data() {
  log "Filtrage cut | awk | sed…"
  cut -f1,22,25,27,28,51,55,56,57,58,59 "$RAW" \
    | awk -F'\t' 'BEGIN{OFS="\t"}
        NR==1{print "isolate_id","collection_date","geo_loc_name","host_disease",
              "isolation_source","number_drugs_resistant","number_amr_genes",
              "number_core_amr_genes","AST_phenotypes","AMR_genotypes",
              "AMR_genotypes_core"; next}
        $10!="NULL" && $10!=""' \
    | sed 's/"//g' > "$OUT"
  [[ -s "$OUT" ]] || die "Fichier filtré vide : $OUT" 3
  log "Fichier filtré : $OUT ($(wc -l < "$OUT") lignes, 11 colonnes)."
  tail -n +2 "$OUT" | cut -f10 | tr ',' '\n' | sed 's/=.*//; s/_.*//' \
    | sed '/^$/d' | sort | uniq -c | sort -rn \
    | awk 'BEGIN{OFS="\t"; print "count","gene"} {print $1,$2}' \
    > results/tables/shell_gene_counts.tsv
  log "Palmarès : results/tables/shell_gene_counts.tsv"
}

find_python() {
  if [[ -n "${PYTHON:-}" ]]; then
    command -v "$PYTHON" >/dev/null || die "PYTHON introuvable." 127
    printf '%s\n' "$PYTHON"; return
  fi
  local p
  for p in python3 python; do
    if command -v "$p" >/dev/null \
      && "$p" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
      printf '%s\n' "$p"; return
    fi
  done
  die "Python 3.10+ introuvable." 127
}

setup_venv() {
  if [[ -x .venv/Scripts/python.exe ]]; then PY=.venv/Scripts/python.exe
  elif [[ -x .venv/bin/python ]]; then PY=.venv/bin/python
  else
    local base; base=$(find_python)
    log "Création de .venv…"
    "$base" -m venv .venv
    if [[ -x .venv/Scripts/python.exe ]]; then PY=.venv/Scripts/python.exe
    else PY=.venv/bin/python; fi
  fi
  local h; h=$(sha256sum requirements.txt | awk '{print $1}')
  if [[ ! -f .venv/.req || "$(cat .venv/.req)" != "$h" ]]; then
    log "Installation des dépendances…"
    "$PY" -m pip install -q --upgrade pip
    "$PY" -m pip install -q -r requirements.txt
    printf '%s\n' "$h" > .venv/.req
  else
    log "Dépendances déjà installées."
  fi
  "$PY" -c 'import pandas, scipy, matplotlib, reportlab, pptx, pypdf, pytest' \
    || die "Dépendances incomplètes." 3
  log "Python : $("$PY" --version 2>&1)"
}

run_tests()    { log "Tests automatiques…"; "$PY" -m pytest -q scripts/tests; }
run_analysis() { log "Analyse Python…"; "$PY" scripts/analysis.py --input "$OUT" --outdir results --config-dir config --raw "$RAW"; }
build_report()   { log "Rapport PDF…"; "$PY" scripts/report.py --results results --out report/rapport.pdf --group-config config/group.env; }
build_slides()   { log "Diapositives…"; "$PY" scripts/make_slides.py --results results --out presentation/presentation.pptx --group-config config/group.env; }

convert_slides() {
  local s=""
  for c in soffice "/c/Program Files/LibreOffice/program/soffice.exe" /usr/bin/libreoffice; do
    if command -v "$c" >/dev/null 2>&1 || [[ -x "$c" ]]; then s="$c"; break; fi
  done
  if [[ -n "$s" ]]; then
    log "Conversion PPTX -> PDF…"
    "$s" --headless --convert-to pdf --outdir presentation presentation/presentation.pptx >/dev/null 2>&1 \
      || log "Conversion impossible ; PPTX conservé."
  else
    log "LibreOffice absent ; PPTX conservé."
  fi
}

checksum_results() {
  log "Sommes de contrôle des résultats…"
  local m="results/checksums.sha256"
  {
    find results/tables results/figures -type f ! -name '.gitkeep'
    printf '%s\n' results/summary.json report/rapport.pdf presentation/presentation.pptx
    if [[ -f presentation/presentation.pdf ]]; then
      printf '%s\n' presentation/presentation.pdf
    fi
  } | LC_ALL=C sort | xargs sha256sum > "$m"
  sha256sum -c "$m" >/dev/null || die "Checksums des résultats invalides." 3
  log "Checksums : $m"
}

archive_results() {
  local a="results/archive/SARM_resultats_$(date '+%Y%m%d_%H%M%S').tar.gz"
  local f=(results/tables results/figures results/summary.json results/checksums.sha256 report/rapport.pdf presentation/presentation.pptx)
  [[ -f presentation/presentation.pdf ]] && f+=(presentation/presentation.pdf)
  log "Archivage…"
  tar -czf "$a" "${f[@]}"
  [[ -s "$a" ]] || die "Archive non créée." 3
  log "Archive : $a"
}

main() {
  parse_args "$@"
  prepare_dirs
  setup_logging
  log "=== Démarrage du pipeline SARM ==="
  log "Répertoire : $(pwd)"
  log "Mode : $([[ "$OFFLINE" -eq 1 ]] && echo hors-ligne || echo normal)"
  download_data
  verify_input
  prepare_data
  setup_venv
  run_tests
  run_analysis
  build_report
  build_slides
  convert_slides
  checksum_results
  archive_results
  chmod +x "$0" scripts/*.py scripts/tests/*.py 2>/dev/null || true
  log "=== Pipeline terminé avec succès ==="
  log "Rapport : report/rapport.pdf"
  log "Diapositives : presentation/presentation.pptx"
  log "Résultats : results/summary.json"
  log "Journal : $LOG"
}

main "$@"
