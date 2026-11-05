#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Projet « Enquête sur une maladie » — SARM / Staphylococcus aureus.

Analyse des gènes de résistance associés :
  1. à la résistance à la méticilline (SARM défini par mecA/mecC) ;
  2. à la multirésistance (MDR = résistance à >= 3 classes d'antibiotiques).

Le script lit le TSV prétraité par le pipeline Shell, construit les variables,
réalise les tests de Fisher avec correction de Benjamini-Hochberg, produit les
tableaux CSV, un résumé JSON et les figures du rapport.

Usage :
    python analysis.py --input data/processed/saureus_filtered.tsv \
        --outdir results --config-dir config
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from scipy.stats import fisher_exact, norm

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Patch
from matplotlib.ticker import NullFormatter
import seaborn as sns

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

MISSING_VALUES = {
    "",
    "NULL",
    "NAN",
    "NA",
    "N/A",
    "MISSING",
    "NOT COLLECTED",
    "NOT APPLICABLE",
    "UNKNOWN",
}
RESISTANT = {"R", "NS"}  # NS = non-susceptible, traité comme résistant
SUSCEPTIBLE = {"S", "I"}  # I = intermédiaire, non classé résistant

MEC_GENES = {"mecA", "mecC"}
SCCMEC_MARKERS = {"mecA", "mecC", "mecI", "mecR1", "bleO"}
MDR_CLASSES_MIN = 3
ALPHA_DEFAULT = 0.05

# Palette cohérente pour le rapport et les diapositives
NAVY = "#1d3557"
TEAL = "#2a9d8f"
ORANGE = "#e76f51"
GOLD = "#e9c46a"
RED = "#c1121f"
BLUE = "#457b9d"
GRAY = "#6c757d"
LIGHT = "#f1f5f9"

FAMILY_COLORS = {
    "Cassette mec": "#1d3557",
    "β-lactamines": "#457b9d",
    "Aminoglycosides": "#e76f51",
    "Macrolides / lincosamides": "#e9c46a",
    "Tétracyclines": "#2a9d8f",
    "Fluoroquinolones": "#8e44ad",
    "Folate / sulfamides": "#f4a261",
    "Phénicols": "#6c757d",
    "Glycopeptides": "#264653",
    "Oxazolidinones": "#a8dadc",
    "Rifampicine": "#bc6c25",
    "Mupirocine": "#d62828",
    "Fosfomycine": "#588157",
    "Efflux": "#adb5bd",
    "Autre": "#adb5bd",
}


# ---------------------------------------------------------------------------
# Utilitaires généraux
# ---------------------------------------------------------------------------


def clean_text(value) -> str:
    """Nettoie une valeur texte issue du TSV (guillemets, espaces)."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    text = str(value).strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        text = text[1:-1]
    return text.strip()


def is_missing(value) -> bool:
    """Vrai si la valeur correspond à une modalité manquante de NCBI."""
    return clean_text(value).upper() in MISSING_VALUES


def split_tokens(value) -> list[str]:
    """Découpe un champ AMR_genotypes en jetons (gène ou variant)."""
    text = clean_text(value)
    if text.upper() in MISSING_VALUES:
        return []
    return [token.strip() for token in text.split(",") if token.strip()]


def parse_ast(value) -> dict[str, str] | None:
    """Transforme AST_phenotypes en dictionnaire {antibiotique: S/I/R/NS/ND}.

    Exemple :
        "oxacillin=R,cefoxitin=S,erythromycin=R"
        -> {"oxacillin": "R", "cefoxitin": "S", "erythromycin": "R"}
    """
    text = clean_text(value)
    if text.upper() in MISSING_VALUES:
        return None
    result: dict[str, str] = {}
    for item in text.split(","):
        if "=" not in item:
            continue
        drug, phenotype = item.split("=", 1)
        drug = drug.strip()
        phenotype = phenotype.strip().upper()
        if drug:
            result[drug] = phenotype
    return result or None


def parse_gene_set(value, known_roots: set[str] | None = None) -> set[str]:
    """Extrait l'ensemble des gènes d'un champ AMR_genotypes.

    Les variants sont ramenés au gène : ``mecA_L94F=POINT`` -> ``mecA``,
    ``gyrA_S84L=POINT`` -> ``gyrA``. Les gènes sans variant sont conservés tels
    quels. ``known_roots`` permet de ne pas confondre un gène contenant un
    underscore avec un variant.
    """
    tokens = split_tokens(value)
    if known_roots is None:
        known_roots = set()
        for token in tokens:
            gene = token.split("=", 1)[0].strip()
            known_roots.add(gene.split("_", 1)[0] if "_" in gene else gene)

    genes: set[str] = set()
    for token in tokens:
        gene = token.split("=", 1)[0].strip()
        if "_" in gene:
            root = gene.split("_", 1)[0]
            if root in known_roots:
                gene = root
        if gene:
            genes.add(gene)
    return genes


def gene_family(gene: str) -> str:
    """Attribue une famille fonctionnelle à un gène (pour les figures)."""
    if gene in {"mecA", "mecC", "mecC2", "mecB", "mec", "mecI", "mecR1", "bleO"}:
        return "Cassette mec"
    if gene in {"blaZ", "blaI", "blaR1", "blaPC1"} or gene.startswith("bla"):
        return "β-lactamines"
    if re.match(r"^(aac|aad|ant|aph|sat|str|spd|spw|armA)", gene):
        return "Aminoglycosides"
    if re.match(r"^(erm|msr|mph|mef|lnu|lsa|vat|vga|vgb)", gene):
        return "Macrolides / lincosamides"
    if gene.startswith("tet") or gene == "rpsJ":
        return "Tétracyclines"
    if gene in {"gyrA", "gyrB", "parC", "parE"}:
        return "Fluoroquinolones"
    if gene.startswith("dfr") or gene in {"folP", "sul1", "sul2"}:
        return "Folate / sulfamides"
    if re.match(r"^(cat|floR|fexA|fexB|cmlA1|cmx)", gene):
        return "Phénicols"
    if gene.startswith("van"):
        return "Glycopeptides"
    if gene in {"cfr", "cfr(B)", "optrA", "poxtA"}:
        return "Oxazolidinones"
    if gene in {"rpoB", "rpoC"}:
        return "Rifampicine"
    if gene in {"mupA", "ileS"}:
        return "Mupirocine"
    if re.match(r"^(fos|murA|glpT|uhpT)", gene):
        return "Fosfomycine"
    if gene.startswith("qnr"):
        return "Fluoroquinolones"
    if gene in {"mepA", "mepR", "acrB", "acrF", "mdtM"}:
        return "Efflux"
    return "Autre"


def bh_fdr(p_values: Iterable[float]) -> np.ndarray:
    """Correction de Benjamini-Hochberg.

    Retourne les q-values dans le même ordre que les p-values d'entrée.
    """
    p = np.asarray(list(p_values), dtype=float)
    n = p.size
    if n == 0:
        return np.array([], dtype=float)
    order = np.argsort(p)
    ranked = p[order]
    q = ranked * n / np.arange(1, n + 1)
    q = np.minimum.accumulate(q[::-1])[::-1]
    q = np.clip(q, 0.0, 1.0)
    out = np.empty_like(q)
    out[order] = q
    return out


def haldane_odds_ratio(a: int, b: int, c: int, d: int) -> tuple[float, float, float]:
    """Odds ratio avec correction de Haldane-Anscombe et IC 95 %.

    La correction +0,5 évite les divisions par zéro et les OR infinis.
    Retourne (OR, borne_basse, borne_haute).
    """
    a2, b2, c2, d2 = a + 0.5, b + 0.5, c + 0.5, d + 0.5
    or_value = (a2 * d2) / (b2 * c2)
    se = math.sqrt(1.0 / a2 + 1.0 / b2 + 1.0 / c2 + 1.0 / d2)
    z = norm.ppf(0.975)
    return or_value, math.exp(math.log(or_value) - z * se), math.exp(math.log(or_value) + z * se)


def safe_divide(numerator: float, denominator: float) -> float:
    """Division protégée retournant NaN si le dénominateur est nul."""
    return float(numerator) / float(denominator) if denominator else float("nan")


def pct(numerator: float, denominator: float) -> float:
    """Pourcentage protégé."""
    return 100.0 * safe_divide(numerator, denominator)


def fmt_int(value) -> str:
    """Formate un entier avec des espaces comme séparateurs de milliers."""
    return f"{int(value):,}".replace(",", " ")


# ---------------------------------------------------------------------------
# Lecture et préparation des données
# ---------------------------------------------------------------------------


def load_drug_classes(path: Path) -> dict[str, str]:
    """Charge le mapping antibiotique -> classe depuis config/drug_classes.tsv."""
    if not path.exists():
        raise FileNotFoundError(f"Mapping des classes introuvable : {path}")
    table = pd.read_csv(path, sep="\t", comment="#", dtype=str)
    if not {"drug", "class"}.issubset(table.columns):
        raise ValueError(f"{path} doit contenir les colonnes 'drug' et 'class'.")
    return dict(zip(table["drug"].str.strip(), table["class"].str.strip()))


def read_metadata(path: Path) -> pd.DataFrame:
    """Lit le TSV prétraité et vérifie les colonnes indispensables."""
    if not path.exists():
        raise FileNotFoundError(f"Fichier d'entrée introuvable : {path}")
    df = pd.read_csv(path, sep="\t", dtype=str, low_memory=False)
    if "#label" in df.columns:
        df = df.rename(columns={"#label": "isolate_id"})
    if "isolate_id" not in df.columns:
        df = df.rename(columns={df.columns[0]: "isolate_id"})

    required = {"isolate_id", "AST_phenotypes", "AMR_genotypes"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            "Colonnes obligatoires absentes du fichier : " + ", ".join(sorted(missing))
        )

    for column in ["AST_phenotypes", "AMR_genotypes", "AMR_genotypes_core"]:
        if column not in df.columns:
            df[column] = "NULL"

    df = df.reset_index(drop=True)
    return df


def build_features(df: pd.DataFrame, drug2class: dict[str, str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Construit les variables d'analyse et la matrice de présence des gènes."""
    # Première passe : racines de gènes (pour normaliser les variants)
    raw_token_sets = [split_tokens(value) for value in df["AMR_genotypes"]]
    known_roots: set[str] = set()
    for tokens in raw_token_sets:
        for token in tokens:
            gene = token.split("=", 1)[0].strip()
            known_roots.add(gene.split("_", 1)[0] if "_" in gene else gene)

    gene_sets = [
        parse_gene_set(value, known_roots) for value in df["AMR_genotypes"]
    ]
    df["genes"] = gene_sets

    all_genes = sorted(set().union(*gene_sets)) if gene_sets else []
    gene_index = {gene: idx for idx, gene in enumerate(all_genes)}
    matrix = np.zeros((len(df), len(all_genes)), dtype=bool)
    for row_idx, genes in enumerate(gene_sets):
        for gene in genes:
            col_idx = gene_index.get(gene)
            if col_idx is not None:
                matrix[row_idx, col_idx] = True
    gene_matrix = pd.DataFrame(matrix, index=df.index, columns=all_genes)

    df["mecA"] = (
        gene_matrix["mecA"] if "mecA" in gene_matrix.columns
        else pd.Series(False, index=df.index)
    )
    df["mecC"] = (
        gene_matrix["mecC"] if "mecC" in gene_matrix.columns
        else pd.Series(False, index=df.index)
    )
    df["MRSA_genotype"] = (df["mecA"] | df["mecC"]).astype(int)
    df["MSSA_genotype"] = 1 - df["MRSA_genotype"]

    # Phénotypes AST
    df["AST"] = df["AST_phenotypes"].map(parse_ast)
    df["has_AST"] = df["AST"].notna().astype(int)

    def phenotype_mrsa(ast: dict[str, str] | None) -> float:
        if not ast:
            return np.nan
        oxacillin = ast.get("oxacillin")
        cefoxitin = ast.get("cefoxitin")
        if oxacillin in RESISTANT or cefoxitin in RESISTANT:
            return 1.0
        if oxacillin in SUSCEPTIBLE or cefoxitin in SUSCEPTIBLE:
            return 0.0
        return np.nan

    df["MRSA_phenotype"] = df["AST"].map(phenotype_mrsa)

    def mdr_status(ast: dict[str, str] | None) -> tuple[float, int]:
        """Retourne (MDR 1/0/NaN, nombre de classes testées)."""
        if not ast:
            return np.nan, 0
        classes_tested: set[str] = set()
        classes_resistant: set[str] = set()
        for drug, phenotype in ast.items():
            drug_class = drug2class.get(drug)
            if not drug_class:
                continue
            classes_tested.add(drug_class)
            if phenotype in RESISTANT:
                classes_resistant.add(drug_class)
        if len(classes_tested) < MDR_CLASSES_MIN:
            return np.nan, len(classes_tested)
        return (1.0 if len(classes_resistant) >= MDR_CLASSES_MIN else 0.0), len(classes_tested)

    mdr_values = df["AST"].map(mdr_status)
    df["MDR"] = [value[0] for value in mdr_values]
    df["n_classes_tested"] = [value[1] for value in mdr_values]

    # Année (extraction robuste, même si la date est partielle)
    df["year"] = (
        df["collection_date"]
        .astype(str)
        .str.extract(r"\b(19\d{2}|20\d{2})\b", expand=False)
        .astype(float)
    )

    return df, gene_matrix


# ---------------------------------------------------------------------------
# Statistiques
# ---------------------------------------------------------------------------


def association_table(
    df: pd.DataFrame,
    gene_matrix: pd.DataFrame,
    group_column: str,
    cohort_mask: pd.Series,
    *,
    exclude: set[str] | None = None,
    min_count: int = 10,
    min_prevalence: float = 0.01,
    max_prevalence: float = 0.95,
    alpha: float = ALPHA_DEFAULT,
) -> pd.DataFrame:
    """Teste l'association présence/absence de chaque gène avec un groupe.

    Le groupe est défini par ``group_column`` (valeurs 0/1). Le test est un
    Fisher exact bilatéral ; l'odds ratio est calculé avec correction de
    Haldane-Anscombe ; les q-values sont obtenues par Benjamini-Hochberg.
    """
    exclude = exclude or set()
    cohort_mask = cohort_mask.fillna(False).astype(bool)
    cohort = df.loc[cohort_mask].copy()
    if cohort.empty:
        return pd.DataFrame(
            columns=[
                "gene", "family", "n_group", "n_control", "a", "b", "c", "d",
                "prevalence_group", "prevalence_control", "risk_difference",
                "odds_ratio", "or_ci_low", "or_ci_high", "p_value", "q_value",
                "significant",
            ]
        )

    group = pd.to_numeric(cohort[group_column], errors="coerce")
    valid = group.notna()
    cohort = cohort.loc[valid]
    group = group.loc[valid].astype(int)
    n_group = int((group == 1).sum())
    n_control = int((group == 0).sum())
    if n_group == 0 or n_control == 0:
        return pd.DataFrame()

    matrix = gene_matrix.loc[cohort.index]
    rows: list[dict] = []
    for gene in matrix.columns:
        if gene in exclude:
            continue
        present = matrix[gene].to_numpy(dtype=bool)
        group_arr = group.to_numpy(dtype=int)
        a = int(np.sum(present & (group_arr == 1)))
        b = n_group - a
        c = int(np.sum(present & (group_arr == 0)))
        d = n_control - c
        if a + c < min_count:
            continue
        prev_group = safe_divide(a, n_group)
        prev_control = safe_divide(c, n_control)
        if max(prev_group, prev_control) < min_prevalence:
            continue
        # Les gènes intrinsèques présents chez presque tous les isolats (mepA,
        # tet(38)...) ne discriminent pas les groupes et donnent des OR trompeurs.
        if min(prev_group, prev_control) >= max_prevalence:
            continue
        _, p_value = fisher_exact([[a, b], [c, d]], alternative="two-sided")
        or_value, ci_low, ci_high = haldane_odds_ratio(a, b, c, d)
        rows.append(
            {
                "gene": gene,
                "family": gene_family(gene),
                "n_group": n_group,
                "n_control": n_control,
                "a": a,
                "b": b,
                "c": c,
                "d": d,
                "prevalence_group": prev_group,
                "prevalence_control": prev_control,
                "risk_difference": prev_group - prev_control,
                "odds_ratio": or_value,
                "or_ci_low": ci_low,
                "or_ci_high": ci_high,
                "p_value": p_value,
            }
        )

    result = pd.DataFrame(rows)
    if result.empty:
        return result
    result["q_value"] = bh_fdr(result["p_value"].to_numpy())
    result["significant"] = (result["q_value"] < alpha).astype(int)
    result = result.sort_values(["q_value", "odds_ratio"], ascending=[True, False])
    return result.reset_index(drop=True)


def cohort_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Construit le tableau de description de la cohorte."""
    total = len(df)
    n_mecA = int(df["mecA"].sum())
    n_mecC = int(df["mecC"].sum())
    n_mrsa_geno = int(df["MRSA_genotype"].sum())
    n_mssa_geno = total - n_mrsa_geno
    n_ast = int(df["has_AST"].sum())
    n_pheno_known = int(df["MRSA_phenotype"].notna().sum())
    n_mrsa_pheno = int((df["MRSA_phenotype"] == 1).sum())
    n_mssa_pheno = int((df["MRSA_phenotype"] == 0).sum())
    n_mdr_known = int(df["MDR"].notna().sum())
    n_mdr = int((df["MDR"] == 1).sum())
    mrsa_mdr_known = df.loc[df["MRSA_phenotype"] == 1, "MDR"].notna().sum()
    mrsa_mdr = int((df.loc[df["MRSA_phenotype"] == 1, "MDR"] == 1).sum())
    mssa_mdr_known = df.loc[df["MRSA_phenotype"] == 0, "MDR"].notna().sum()
    mssa_mdr = int((df.loc[df["MRSA_phenotype"] == 0, "MDR"] == 1).sum())

    rows = [
        ("Isolats analysés", total, total, "Toutes les lignes du snapshot"),
        ("mecA détecté", n_mecA, total, "Génotype AMR"),
        ("mecC détecté", n_mecC, total, "Génotype AMR"),
        ("SARM génotypique (mecA ou mecC)", n_mrsa_geno, total, "Définition principale"),
        ("SARM génotypique sans mecA/mecC", n_mssa_geno, total, "Comparateur MSSA"),
        ("Isolats avec AST", n_ast, total, "Phénotypes disponibles"),
        ("Phénotype SARM (oxacilline ou céfoxitine R)", n_mrsa_pheno, n_pheno_known, "Sous-cohorte AST"),
        ("Phénotype MSSA", n_mssa_pheno, n_pheno_known, "Sous-cohorte AST"),
        ("MDR évaluable", n_mdr_known, n_ast, ">= 3 classes testées"),
        ("MDR (>= 3 classes R)", n_mdr, n_mdr_known, "Toute la sous-cohorte AST"),
        ("MDR chez les SARM phénotypiques", mrsa_mdr, mrsa_mdr_known, "Question principale"),
        ("MDR chez les MSSA phénotypiques", mssa_mdr, mssa_mdr_known, "Comparateur"),
    ]
    table = pd.DataFrame(rows, columns=["metric", "n", "denominator", "comment"])
    table["percent"] = table.apply(
        lambda row: round(pct(row["n"], row["denominator"]), 2), axis=1
    )
    return table


def phenotype_concordance(df: pd.DataFrame) -> pd.DataFrame:
    """Compare le génotype mecA/mecC et le phénotype oxacilline/céfoxitine."""
    sub = df.loc[df["MRSA_phenotype"].notna()].copy()
    tp = int(((sub["MRSA_genotype"] == 1) & (sub["MRSA_phenotype"] == 1)).sum())
    fn = int(((sub["MRSA_genotype"] == 1) & (sub["MRSA_phenotype"] == 0)).sum())
    fp = int(((sub["MRSA_genotype"] == 0) & (sub["MRSA_phenotype"] == 1)).sum())
    tn = int(((sub["MRSA_genotype"] == 0) & (sub["MRSA_phenotype"] == 0)).sum())
    n = tp + fn + fp + tn
    sensitivity = safe_divide(tp, tp + fn)
    specificity = safe_divide(tn, tn + fp)
    ppv = safe_divide(tp, tp + fp)
    npv = safe_divide(tn, tn + fn)
    observed = safe_divide(tp + tn, n)
    expected = safe_divide(
        (tp + fp) * (tp + fn) + (fn + tn) * (fp + tn), n * n
    )
    kappa = safe_divide(observed - expected, 1 - expected)
    return pd.DataFrame(
        [
            {
                "n_compared": n,
                "true_positive": tp,
                "false_negative": fn,
                "false_positive": fp,
                "true_negative": tn,
                "sensitivity": sensitivity,
                "specificity": specificity,
                "ppv": ppv,
                "npv": npv,
                "cohen_kappa": kappa,
            }
        ]
    )


def mdr_by_class(df: pd.DataFrame, drug2class: dict[str, str]) -> pd.DataFrame:
    """Compte les résistances par classe d'antibiotiques dans la sous-cohorte AST."""
    sub = df.loc[df["AST"].notna()].copy()
    classes = sorted(set(drug2class.values()))
    rows = []
    for drug_class in classes:
        tested = 0
        resistant = 0
        resistant_mrsa = 0
        resistant_mssa = 0
        for _, row in sub.iterrows():
            ast = row["AST"]
            if not ast:
                continue
            drugs = [drug for drug in ast if drug2class.get(drug) == drug_class]
            if not drugs:
                continue
            tested += 1
            if any(ast[drug] in RESISTANT for drug in drugs):
                resistant += 1
                if row["MRSA_phenotype"] == 1:
                    resistant_mrsa += 1
                elif row["MRSA_phenotype"] == 0:
                    resistant_mssa += 1
        if tested:
            rows.append(
                {
                    "drug_class": drug_class,
                    "n_tested": tested,
                    "n_resistant": resistant,
                    "percent_resistant": round(pct(resistant, tested), 2),
                    "n_resistant_mrsa": resistant_mrsa,
                    "n_resistant_mssa": resistant_mssa,
                }
            )
    result = pd.DataFrame(rows).sort_values("percent_resistant", ascending=False)
    return result.reset_index(drop=True)


def temporal_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Prévalence du génotype SARM par année (au moins 30 isolats)."""
    sub = df.loc[df["year"].notna() & df["year"].between(1990, 2026)].copy()
    rows = []
    for year, group in sub.groupby("year"):
        n = len(group)
        if n < 30:
            continue
        k = int(group["MRSA_genotype"].sum())
        p = safe_divide(k, n)
        # Intervalle de Wilson à 95 %
        z = 1.959963984540054
        denom = 1 + z * z / n
        center = (p + z * z / (2 * n)) / denom
        half = z * math.sqrt((p * (1 - p) / n) + (z * z / (4 * n * n))) / denom
        rows.append(
            {
                "year": int(year),
                "n_isolates": n,
                "n_mrsa": k,
                "prevalence": p,
                "ci_low": max(0.0, center - half),
                "ci_high": min(1.0, center + half),
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def configure_matplotlib() -> None:
    """Style commun des figures."""
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.titlesize": 10.5,
            "axes.titleweight": "bold",
            "axes.labelsize": 9,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "figure.dpi": 150,
            "savefig.dpi": 300,
            "savefig.bbox": "tight",
            "savefig.facecolor": "white",
        }
    )


def save_figure(fig: plt.Figure, path: Path) -> None:
    """Sauvegarde une figure et ferme l'objet."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def plot_pipeline(path: Path) -> None:
    """Schéma du pipeline reproductible."""
    fig, ax = plt.subplots(figsize=(7.4, 2.15))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 3)
    ax.axis("off")

    boxes = [
        (0.15, "NCBI FTP\n164 Mo", "#e8eef7"),
        (2.55, "run.sh\nSHA-256 + taille", "#dce9e6"),
        (4.95, "Shell\ncut | awk | sed", "#fbe7df"),
        (7.35, "Python\nFisher + BH", "#f7efd2"),
        (9.75, "Résultats\nCSV · JSON\nfigures", "#e8eef7"),
    ]
    width, height, y = 2.05, 1.15, 1.0
    for x, label, color in boxes:
        box = FancyBboxPatch(
            (x, y), width, height,
            boxstyle="round,pad=0.03,rounding_size=0.12",
            facecolor=color, edgecolor="#ffffff", linewidth=0.8,
        )
        ax.add_patch(box)
        ax.text(x + width / 2, y + height / 2, label, ha="center", va="center",
                fontsize=8.2, color=NAVY, linespacing=1.25)

    for i in range(len(boxes) - 1):
        x1 = boxes[i][0] + width
        x2 = boxes[i + 1][0]
        ax.add_patch(
            FancyArrowPatch(
                (x1 + 0.03, y + height / 2),
                (x2 - 0.03, y + height / 2),
                arrowstyle="-|>", mutation_scale=10, color=GRAY, linewidth=1.0,
            )
        )

    ax.text(
        6.0, 0.40,
        "logs horodatés  ·  checksums vérifiés  ·  archive tar datée  ·  rapport PDF",
        ha="center", va="center", fontsize=7.4, color=GRAY,
    )
    ax.text(
        6.0, 2.55,
        "De la donnée brute au rapport, sans intervention manuelle",
        ha="center", va="center", fontsize=9.6, color=NAVY, fontweight="bold",
    )
    save_figure(fig, path)


def plot_cohort(summary: dict, path: Path) -> None:
    """Figure 1 : effectifs de la cohorte et prévalence de la MDR."""
    cohort = summary["cohort"]
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.0), gridspec_kw={"width_ratios": [1.55, 1]})

    labels = [
        "Isolats analysés",
        "SARM génotypique\n(mecA/mecC)",
        "Isolats avec AST",
        "SARM phénotypique",
        "SARM + MDR",
    ]
    values = [
        cohort["n_isolates"],
        cohort["n_mrsa_genotype"],
        cohort["n_ast"],
        cohort["n_mrsa_phenotype"],
        cohort["n_mrsa_mdr"],
    ]
    colors = [NAVY, TEAL, GOLD, ORANGE, RED]
    y = np.arange(len(labels))[::-1]
    axes[0].barh(y, values, color=colors, height=0.62)
    axes[0].set_yticks(y)
    axes[0].set_yticklabels(labels, fontsize=8)
    axes[0].set_xscale("log")
    axes[0].set_xlabel("Nombre d'isolats (échelle log)")
    axes[0].set_title("A. Effectifs du jeu de données", loc="left")
    for yi, value in zip(y, values):
        axes[0].text(value * 1.12, yi, fmt_int(value), va="center", fontsize=8, color=NAVY)
    axes[0].set_xlim(100, max(values) * 3)

    groups = ["SARM", "MSSA"]
    prevalence = [cohort["mdr_in_mrsa_percent"] / 100, cohort["mdr_in_mssa_percent"] / 100]
    counts = [cohort["n_mrsa_mdr"], cohort["n_mssa_mdr"]]
    bars = axes[1].bar(groups, prevalence, color=[ORANGE, TEAL], width=0.55)
    axes[1].set_ylim(0, 0.75)
    axes[1].set_ylabel("Proportion de MDR")
    axes[1].set_title("B. MDR selon le phénotype", loc="left")
    axes[1].yaxis.set_major_formatter(lambda x, _: f"{x*100:.0f} %")
    for bar, prev, count in zip(bars, prevalence, counts):
        axes[1].text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.025,
            f"{prev*100:.1f} %\n(n = {fmt_int(count)})",
            ha="center", va="bottom", fontsize=8,
        )

    fig.text(
        0.01, -0.03,
        "MDR = résistance à au moins 3 classes d'antibiotiques (AST). "
        "SARM phénotypique = oxacilline ou céfoxitine R.",
        fontsize=7, color=GRAY,
    )
    fig.tight_layout()
    save_figure(fig, path)


def plot_gene_associations(
    table: pd.DataFrame,
    path: Path,
    *,
    title: str,
    xlabel: str,
    max_genes: int = 15,
    note: str = "",
) -> None:
    """Dessine un graphique en forêt des gènes associés (OR + IC 95 %)."""
    if table.empty:
        fig, ax = plt.subplots(figsize=(7.2, 2.0))
        ax.axis("off")
        ax.text(0.5, 0.5, "Aucun gène significatif avec les filtres choisis.",
                ha="center", va="center", fontsize=10, color=GRAY)
        save_figure(fig, path)
        return

    data = table.head(max_genes).copy().iloc[::-1].reset_index(drop=True)
    y = np.arange(len(data))
    low = 1.0
    high = min(1e4, max(2.0, float(data["or_ci_high"].max()) * 1.15))
    rotated_ticks = high > 100
    bottom = 0.25 if rotated_ticks else 0.14
    fig, ax = plt.subplots(figsize=(6.4, 0.42 * len(data) + 2.1))
    fig.subplots_adjust(left=0.24, right=0.66, top=0.90, bottom=bottom)

    for yi, (_, row) in zip(y, data.iterrows()):
        color = FAMILY_COLORS.get(row["family"], FAMILY_COLORS["Autre"])
        ax.hlines(yi, row["or_ci_low"], row["or_ci_high"], color=color, linewidth=1.8, alpha=0.85)
        ax.plot(row["odds_ratio"], yi, "o", color=color, markersize=6.5, zorder=3)

    ax.axvline(1, color=GRAY, linestyle="--", linewidth=1)
    ax.set_xscale("log")
    ax.set_xlim(low, high)
    ax.set_yticks(y)
    ax.set_yticklabels(data["gene"], fontsize=9.2)
    ax.set_xlabel(xlabel, fontsize=9.2)
    ax.set_title(title, loc="left", pad=16, fontsize=10.6)
    ax.grid(axis="x", color="#e5e7eb", linewidth=0.7)
    ax.set_axisbelow(True)

    # Graduations lisibles (pas de notation scientifique)
    candidates = [1, 2, 3, 5, 7, 10, 15, 20, 30, 50, 100, 200, 500, 1000, 2000, 5000]
    ticks = [tick for tick in candidates if low <= tick <= high]
    if ticks:
        ax.set_xticks(ticks)
        ax.set_xticklabels([str(tick) for tick in ticks])
    if rotated_ticks:
        plt.setp(ax.get_xticklabels(), rotation=45, ha="right", fontsize=7.5)
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.tick_params(axis="x", pad=2)

    # Prévalences à droite, en dehors de la zone de tracé
    ax.text(
        1.02, 0.998, "SARM → MSSA",
        transform=ax.transAxes, ha="left", va="bottom",
        fontsize=7.6, color=GRAY, fontweight="bold", clip_on=False,
    )
    for yi, (_, row) in zip(y, data.iterrows()):
        ax.text(
            1.02, yi,
            f"{row['prevalence_group']*100:.1f} % → {row['prevalence_control']*100:.1f} %",
            transform=ax.get_yaxis_transform(), ha="left", va="center",
            fontsize=8.0, color=GRAY, clip_on=False,
        )

    families = [family for family in FAMILY_COLORS if family in set(data["family"])]
    handles = [Patch(facecolor=FAMILY_COLORS[family], label=family) for family in families]
    legend_y = 0.05 if rotated_ticks else 0.005
    fig.legend(
        handles=handles, loc="lower center", bbox_to_anchor=(0.45, legend_y),
        fontsize=7.2, frameon=False, ncol=4, handlelength=1.2, columnspacing=1.0,
    )

    if note:
        note_y = -0.02 if rotated_ticks else -0.05
        fig.text(0.01, note_y, note, fontsize=7.0, color=GRAY)
    save_figure(fig, path)


def plot_cooccurrence(
    df: pd.DataFrame,
    gene_matrix: pd.DataFrame,
    genes: list[str],
    path: Path,
) -> None:
    """Heatmap de co-occurrence (phi) des gènes dans les SARM génotypiques."""
    genes = [gene for gene in genes if gene in gene_matrix.columns]
    if len(genes) < 3:
        return
    sub = gene_matrix.loc[df["MRSA_genotype"] == 1, genes].astype(int)
    n = len(sub)
    phi = pd.DataFrame(np.eye(len(genes)), index=genes, columns=genes, dtype=float)
    for i, gene_i in enumerate(genes):
        for j in range(i + 1, len(genes)):
            gene_j = genes[j]
            a = int(((sub[gene_i] == 1) & (sub[gene_j] == 1)).sum())
            b = int(((sub[gene_i] == 1) & (sub[gene_j] == 0)).sum())
            c = int(((sub[gene_i] == 0) & (sub[gene_j] == 1)).sum())
            d = int(((sub[gene_i] == 0) & (sub[gene_j] == 0)).sum())
            denom = math.sqrt((a + b) * (c + d) * (a + c) * (b + d))
            value = (a * d - b * c) / denom if denom else 0.0
            phi.loc[gene_i, gene_j] = value
            phi.loc[gene_j, gene_i] = value

    grid = sns.clustermap(
        phi,
        cmap="RdBu_r",
        center=0,
        vmin=-1,
        vmax=1,
        figsize=(7.2, 6.4),
        linewidths=0.5,
        linecolor="white",
        method="average",
        metric="euclidean",
        cbar_pos=(0.02, 0.84, 0.035, 0.13),
        cbar_kws={"label": "φ"},
    )
    grid.fig.suptitle(
        f"Co-occurrence des gènes dans les SARM génotypiques (n = {fmt_int(n)})",
        y=1.02, fontsize=10.5, color=NAVY, fontweight="bold",
    )
    grid.ax_heatmap.set_xlabel("")
    grid.ax_heatmap.set_ylabel("")
    plt.setp(grid.ax_heatmap.get_xticklabels(), rotation=45, ha="right", fontsize=7.5)
    plt.setp(grid.ax_heatmap.get_yticklabels(), rotation=0, fontsize=7.5)
    grid.fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(grid.fig)


def plot_temporal(temporal: pd.DataFrame, path: Path) -> None:
    """Figure supplémentaire : prévalence du génotype SARM par année."""
    if temporal.empty:
        return
    fig, ax = plt.subplots(figsize=(7.2, 2.8))
    ax.fill_between(
        temporal["year"], temporal["ci_low"] * 100, temporal["ci_high"] * 100,
        color=TEAL, alpha=0.18, linewidth=0,
    )
    ax.plot(temporal["year"], temporal["prevalence"] * 100, color=TEAL, linewidth=2)
    ax.scatter(
        temporal["year"], temporal["prevalence"] * 100,
        s=np.clip(temporal["n_isolates"] / 200, 10, 80),
        color=TEAL, edgecolor="white", linewidth=0.6, zorder=3,
    )
    ax.set_ylim(0, 100)
    ax.set_xlabel("Année de collecte")
    ax.set_ylabel("SARM génotypique (%)")
    ax.set_title("Prévalence du génotype SARM par année (n >= 30)", loc="left")
    ax.grid(axis="y", color="#e5e7eb", linewidth=0.7)
    ax.set_axisbelow(True)
    fig.text(
        0.01, -0.04,
        "La taille des points est proportionnelle au nombre d'isolats. "
        "Les dates de collecte sont manquantes pour une grande partie du snapshot.",
        fontsize=6.8, color=GRAY,
    )
    fig.tight_layout()
    save_figure(fig, path)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def build_summary(
    df: pd.DataFrame,
    cohort: pd.DataFrame,
    concordance: pd.DataFrame,
    mrsa_assoc: pd.DataFrame,
    mdr_assoc: pd.DataFrame,
    temporal: pd.DataFrame,
    raw_path: Path | None,
    raw_sha256: str | None,
) -> dict:
    """Construit le résumé JSON utilisé par le rapport et les diapositives."""
    def get_metric(name: str) -> dict:
        row = cohort.loc[cohort["metric"] == name]
        if row.empty:
            return {"n": 0, "denominator": 0, "percent": 0.0}
        row = row.iloc[0]
        return {
            "n": int(row["n"]),
            "denominator": int(row["denominator"]),
            "percent": float(row["percent"]),
        }

    total = len(df)
    n_mrsa_geno = int(df["MRSA_genotype"].sum())
    n_ast = int(df["has_AST"].sum())
    n_pheno_known = int(df["MRSA_phenotype"].notna().sum())
    n_mrsa_pheno = int((df["MRSA_phenotype"] == 1).sum())
    n_mssa_pheno = int((df["MRSA_phenotype"] == 0).sum())
    n_mdr_known = int(df["MDR"].notna().sum())
    n_mdr = int((df["MDR"] == 1).sum())
    mrsa_mdr_known = int(df.loc[df["MRSA_phenotype"] == 1, "MDR"].notna().sum())
    mrsa_mdr = int((df.loc[df["MRSA_phenotype"] == 1, "MDR"] == 1).sum())
    mssa_mdr_known = int(df.loc[df["MRSA_phenotype"] == 0, "MDR"].notna().sum())
    mssa_mdr = int((df.loc[df["MRSA_phenotype"] == 0, "MDR"] == 1).sum())

    def top_records(table: pd.DataFrame, n: int = 10) -> list[dict]:
        if table.empty:
            return []
        out = []
        for _, row in table.head(n).iterrows():
            out.append(
                {
                    "gene": row["gene"],
                    "family": row["family"],
                    "prevalence_group": float(row["prevalence_group"]),
                    "prevalence_control": float(row["prevalence_control"]),
                    "odds_ratio": float(row["odds_ratio"]),
                    "or_ci_low": float(row["or_ci_low"]),
                    "or_ci_high": float(row["or_ci_high"]),
                    "p_value": float(row["p_value"]),
                    "q_value": float(row["q_value"]),
                }
            )
        return out

    concordance_row = concordance.iloc[0].to_dict() if not concordance.empty else {}
    temporal_range = {}
    if not temporal.empty:
        temporal_range = {
            "year_min": int(temporal["year"].min()),
            "year_max": int(temporal["year"].max()),
            "n_years": int(len(temporal)),
        }

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "dataset": {
            "name": "NCBI Pathogen Detection — Staphylococcus aureus",
            "snapshot": "PDG000000073.1314",
            "file": "PDG000000073.1314.metadata.tsv",
            "bytes": int(raw_path.stat().st_size) if raw_path and raw_path.exists() else None,
            "sha256": raw_sha256,
            "n_isolates": total,
        },
        "cohort": {
            "n_isolates": total,
            "n_mecA": int(df["mecA"].sum()),
            "n_mecC": int(df["mecC"].sum()),
            "n_mrsa_genotype": n_mrsa_geno,
            "n_mssa_genotype": total - n_mrsa_geno,
            "mrsa_genotype_percent": round(pct(n_mrsa_geno, total), 2),
            "n_ast": n_ast,
            "ast_percent": round(pct(n_ast, total), 2),
            "n_phenotype_known": n_pheno_known,
            "n_mrsa_phenotype": n_mrsa_pheno,
            "n_mssa_phenotype": n_mssa_pheno,
            "mrsa_phenotype_percent": round(pct(n_mrsa_pheno, n_pheno_known), 2),
            "n_mdr_known": n_mdr_known,
            "n_mdr": n_mdr,
            "mdr_percent": round(pct(n_mdr, n_mdr_known), 2),
            "n_mrsa_mdr": mrsa_mdr,
            "n_mrsa_mdr_known": mrsa_mdr_known,
            "mdr_in_mrsa_percent": round(pct(mrsa_mdr, mrsa_mdr_known), 2),
            "n_mssa_mdr": mssa_mdr,
            "n_mssa_mdr_known": mssa_mdr_known,
            "mdr_in_mssa_percent": round(pct(mssa_mdr, mssa_mdr_known), 2),
            "metrics": {
                "n_isolates": get_metric("Isolats analysés"),
                "n_mrsa_genotype": get_metric("SARM génotypique (mecA ou mecC)"),
                "n_ast": get_metric("Isolats avec AST"),
                "n_mrsa_phenotype": get_metric("Phénotype SARM (oxacilline ou céfoxitine R)"),
                "n_mdr": get_metric("MDR (>= 3 classes R)"),
            },
        },
        "concordance": {
            key: (float(value) if isinstance(value, (int, float, np.floating)) else value)
            for key, value in concordance_row.items()
        },
        "top_mrsa_genes": top_records(mrsa_assoc, 12),
        "top_mdr_genes": top_records(mdr_assoc, 12),
        "temporal": temporal_range,
        "software": {
            "python": sys.version.split()[0],
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "scipy": __import__("scipy").__version__,
            "matplotlib": matplotlib.__version__,
            "seaborn": sns.__version__,
        },
    }


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Calcule le SHA-256 d'un fichier par blocs."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(chunk_size), b""):
            digest.update(block)
    return digest.hexdigest()


def write_csv(table: pd.DataFrame, path: Path) -> None:
    """Écrit un CSV en créant le dossier si nécessaire."""
    path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(path, index=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Analyse SARM : gènes associés à la méticilline et à la multirésistance.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemple :\n"
            "  python analysis.py --input data/processed/saureus_filtered.tsv "
            "--outdir results --raw data/raw/PDG000000073.1314.metadata.tsv"
        ),
    )
    parser.add_argument("--input", required=True, type=Path,
                        help="TSV prétraité par le pipeline Shell.")
    parser.add_argument("--outdir", default=Path("results"), type=Path,
                        help="Dossier de sortie (défaut : results).")
    parser.add_argument("--config-dir", default=Path("config"), type=Path,
                        help="Dossier contenant drug_classes.tsv (défaut : config).")
    parser.add_argument("--raw", type=Path, default=None,
                        help="Fichier brut optionnel, pour le SHA-256 du résumé.")
    parser.add_argument("--min-count", type=int, default=10,
                        help="Nombre minimal d'isolats portant le gène (défaut : 10).")
    parser.add_argument("--min-prevalence", type=float, default=0.01,
                        help="Prévalence minimale dans au moins un groupe (défaut : 0.01).")
    parser.add_argument("--max-prevalence", type=float, default=0.95,
                        help="Prévalence maximale dans les deux groupes pour exclure "
                             "les gènes intrinsèques quasi universels (défaut : 0.95).")
    parser.add_argument("--alpha", type=float, default=ALPHA_DEFAULT,
                        help="Seuil de significativité après BH (défaut : 0.05).")
    parser.add_argument("--max-figure-genes", type=int, default=10,
                        help="Nombre de gènes affichés sur les figures (défaut : 10).")
    args = parser.parse_args(argv)

    try:
        configure_matplotlib()
        outdir = args.outdir.resolve()
        tables_dir = outdir / "tables"
        figures_dir = outdir / "figures"
        supp_dir = figures_dir / "supplementaires"
        tables_dir.mkdir(parents=True, exist_ok=True)
        figures_dir.mkdir(parents=True, exist_ok=True)
        supp_dir.mkdir(parents=True, exist_ok=True)

        drug2class = load_drug_classes(args.config_dir / "drug_classes.tsv")
        df = read_metadata(args.input)
        df, gene_matrix = build_features(df, drug2class)

        print(f"[analysis] {len(df):,} isolats lus".replace(",", " "))
        print(f"[analysis] {len(gene_matrix.columns)} gènes distincts après normalisation")

        cohort = cohort_summary(df)
        write_csv(cohort, tables_dir / "cohort_summary.csv")

        concordance = phenotype_concordance(df)
        write_csv(concordance, tables_dir / "phenotype_concordance.csv")

        # 1) SARM génotypique vs MSSA génotypique (toute la cohorte)
        mrsa_geno_assoc = association_table(
            df,
            gene_matrix,
            "MRSA_genotype",
            pd.Series(True, index=df.index),
            exclude=MEC_GENES,
            min_count=args.min_count,
            min_prevalence=args.min_prevalence,
            max_prevalence=args.max_prevalence,
            alpha=args.alpha,
        )
        write_csv(mrsa_geno_assoc, tables_dir / "gene_association_mrsa_genotype.csv")

        # 2) Validation phénotypique (sous-cohorte AST)
        mrsa_pheno_assoc = association_table(
            df,
            gene_matrix,
            "MRSA_phenotype",
            df["MRSA_phenotype"].notna(),
            exclude=MEC_GENES,
            min_count=args.min_count,
            min_prevalence=args.min_prevalence,
            max_prevalence=args.max_prevalence,
            alpha=args.alpha,
        )
        write_csv(mrsa_pheno_assoc, tables_dir / "gene_association_mrsa_phenotype.csv")

        # 3) MDR dans toute la sous-cohorte AST
        mdr_all_assoc = association_table(
            df,
            gene_matrix,
            "MDR",
            df["MDR"].notna(),
            exclude=MEC_GENES,
            min_count=args.min_count,
            min_prevalence=args.min_prevalence,
            max_prevalence=args.max_prevalence,
            alpha=args.alpha,
        )
        write_csv(mdr_all_assoc, tables_dir / "gene_association_mdr_all.csv")

        # 4) MDR chez les SARM phénotypiques (question principale)
        mdr_mrsa_assoc = association_table(
            df,
            gene_matrix,
            "MDR",
            (df["MRSA_phenotype"] == 1) & df["MDR"].notna(),
            exclude=MEC_GENES,
            min_count=args.min_count,
            min_prevalence=args.min_prevalence,
            max_prevalence=args.max_prevalence,
            alpha=args.alpha,
        )
        write_csv(mdr_mrsa_assoc, tables_dir / "gene_association_mdr_mrsa.csv")

        # Tableaux « top gènes » : enrichis, hors marqueurs de cassette mec
        def top_enriched(table: pd.DataFrame, n: int, exclude: set[str]) -> pd.DataFrame:
            if table.empty:
                return table
            subset = table.loc[
                (table["q_value"] < args.alpha) & (~table["gene"].isin(exclude))
            ].copy()
            subset = subset.sort_values("odds_ratio", ascending=False).head(n)
            return subset.reset_index(drop=True)

        top_mrsa = top_enriched(mrsa_geno_assoc, 20, SCCMEC_MARKERS)
        write_csv(top_mrsa, tables_dir / "top_genes_mrsa.csv")
        top_mdr = top_enriched(mdr_mrsa_assoc, 20, {"mecA", "mecC"})
        write_csv(top_mdr, tables_dir / "top_genes_mdr.csv")

        mdr_classes = mdr_by_class(df, drug2class)
        write_csv(mdr_classes, tables_dir / "mdr_by_class.csv")

        temporal = temporal_summary(df)
        write_csv(temporal, tables_dir / "temporal_mrsa.csv")

        # Résumé JSON
        raw_sha256 = None
        if args.raw and args.raw.exists():
            print(f"[analysis] calcul du SHA-256 de {args.raw.name} ...")
            raw_sha256 = sha256_file(args.raw)
        summary = build_summary(
            df, cohort, concordance, mrsa_geno_assoc, mdr_mrsa_assoc, temporal,
            args.raw, raw_sha256,
        )
        summary_path = outdir / "summary.json"
        with summary_path.open("w", encoding="utf-8") as handle:
            json.dump(summary, handle, ensure_ascii=False, indent=2)

        # Figures
        plot_pipeline(figures_dir / "fig00_pipeline.png")
        plot_cohort(summary, figures_dir / "fig01_cohort.png")
        plot_gene_associations(
            top_mrsa,
            figures_dir / "fig02_mrsa_genes.png",
            title="Gènes co-portés avec mecA/mecC (hors cassette SCCmec)",
            xlabel="Odds ratio (IC 95 %, échelle log)",
            max_genes=args.max_figure_genes,
            note=(
                "SARM génotypique vs MSSA génotypique ; test de Fisher bilatéral ; "
                "q < 0,05 après correction de Benjamini-Hochberg. "
                "Les valeurs à droite sont les prévalences SARM → MSSA."
            ),
        )
        cooccurrence_genes = list(top_mrsa["gene"].head(10)) if not top_mrsa.empty else []
        plot_cooccurrence(df, gene_matrix, cooccurrence_genes,
                          figures_dir / "fig03_cooccurrence.png")
        plot_gene_associations(
            top_mdr,
            figures_dir / "fig04_mdr_genes.png",
            title="Gènes associés à la multirésistance chez les SARM phénotypiques",
            xlabel="Odds ratio (IC 95 %, échelle log)",
            max_genes=min(args.max_figure_genes, 12),
            note=(
                "MDR = résistance à >= 3 classes d'antibiotiques ; "
                "comparaison MDR vs non-MDR parmi les SARM phénotypiques (oxacilline/céfoxitine R). "
                "Fisher bilatéral ; q < 0,05 (BH)."
            ),
        )
        plot_temporal(temporal, supp_dir / "fig05_temporal.png")

        print(f"[analysis] tableaux : {tables_dir}")
        print(f"[analysis] figures  : {figures_dir}")
        print(f"[analysis] résumé   : {summary_path}")
        return 0

    except FileNotFoundError as error:
        print(f"[analysis] ERREUR : {error}", file=sys.stderr)
        return 2
    except ValueError as error:
        print(f"[analysis] ERREUR de données : {error}", file=sys.stderr)
        return 3
    except Exception as error:  # pragma: no cover - garde-fou pour le pipeline
        print(f"[analysis] ERREUR inattendue : {error}", file=sys.stderr)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
