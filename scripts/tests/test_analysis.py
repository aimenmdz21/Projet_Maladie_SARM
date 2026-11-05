#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests automatisés du pipeline SARM.

Les tests unitaires vérifient les fonctions critiques (parsing, correction de
Benjamini-Hochberg, odds ratio, table 2×2). Le test d'intégration construit un
petit jeu de données synthétique, exécute analysis.py puis report.py et vérifie
que les sorties annoncées sont produites et que le rapport fait au plus 4 pages.

Exécution :
    .venv/Scripts/python.exe -m pytest -q scripts/tests
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pypdf import PdfReader

import analysis
import report


# ---------------------------------------------------------------------------
# Tests unitaires
# ---------------------------------------------------------------------------


def test_parse_ast_normal_and_missing():
    parsed = analysis.parse_ast('"oxacillin=R,cefoxitin=S,erythromycin=I"')
    assert parsed == {
        "oxacillin": "R",
        "cefoxitin": "S",
        "erythromycin": "I",
    }
    assert analysis.parse_ast("NULL") is None
    assert analysis.parse_ast("") is None
    assert analysis.parse_ast("not a phenotype") is None


def test_parse_gene_set_normalizes_variants():
    known_roots = {"mecA", "gyrA", "parC", "aac(6')-Ie/aph(2'')-Ia"}
    genes = analysis.parse_gene_set(
        '"mecA_L94F=POINT,gyrA_S84L=POINT,parC_S80Y=POINT,tet(M),'
        'aac(6\')-Ie/aph(2\'\')-Ia"',
        known_roots,
    )
    assert genes == {
        "mecA",
        "gyrA",
        "parC",
        "tet(M)",
        "aac(6')-Ie/aph(2'')-Ia",
    }


def test_bh_fdr_is_monotonic_and_bounded():
    p_values = [0.001, 0.01, 0.2, 0.9]
    q_values = analysis.bh_fdr(p_values)
    assert np.allclose(q_values, [0.004, 0.02, 0.2666666667, 0.9])
    assert np.all(q_values >= np.asarray(p_values))
    assert np.all((q_values >= 0) & (q_values <= 1))
    assert analysis.bh_fdr([]).size == 0


def test_haldane_odds_ratio_and_ci():
    odds_ratio, ci_low, ci_high = analysis.haldane_odds_ratio(20, 10, 5, 25)
    assert odds_ratio == pytest.approx(9.0519, rel=1e-3)
    assert 1.0 < ci_low < odds_ratio < ci_high
    # La correction +0,5 évite un OR infini quand une cellule est nulle.
    finite_or, finite_low, finite_high = analysis.haldane_odds_ratio(10, 90, 0, 100)
    assert np.isfinite(finite_or) and finite_or > 1
    assert finite_low > 0 and finite_high > finite_low


def test_association_table_filters_and_statistics():
    n = 60
    group = pd.Series([1] * 30 + [0] * 30)
    df = pd.DataFrame({"group": group})
    gene_matrix = pd.DataFrame(
        {
            "gene_enrichi": [True] * 25 + [False] * 5 + [True] * 5 + [False] * 25,
            "gene_universel": [True] * n,
            "gene_rare": [True] * 2 + [False] * 28 + [True] * 1 + [False] * 29,
        },
        index=df.index,
    )
    result = analysis.association_table(
        df,
        gene_matrix,
        "group",
        pd.Series(True, index=df.index),
        min_count=10,
        min_prevalence=0.01,
        max_prevalence=0.95,
        alpha=0.05,
    )
    assert "gene_enrichi" in set(result["gene"])
    assert "gene_universel" not in set(result["gene"])
    assert "gene_rare" not in set(result["gene"])
    row = result.loc[result["gene"] == "gene_enrichi"].iloc[0]
    assert (row["a"], row["b"], row["c"], row["d"]) == (25, 5, 5, 25)
    assert row["odds_ratio"] > 1
    assert row["q_value"] < 0.05


# ---------------------------------------------------------------------------
# Jeu de données synthétique pour le test d'intégration
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def demo_results(tmp_path_factory) -> Path:
    base = tmp_path_factory.mktemp("demo_sarm")
    rows = [
        {
            "isolate_id": "MRSA_1",
            "collection_date": "2020",
            "geo_loc_name": "France",
            "host_disease": "NULL",
            "isolation_source": "blood",
            "number_drugs_resistant": "4",
            "number_amr_genes": "4",
            "number_core_amr_genes": "4",
            "AST_phenotypes": "oxacillin=R,erythromycin=R,clindamycin=R,gentamicin=R",
            "AMR_genotypes": "mecA,erm(C),ant(9)-Ia,tet(M)",
            "AMR_genotypes_core": "mecA,erm(C),ant(9)-Ia,tet(M)",
        },
        {
            "isolate_id": "MRSA_2",
            "collection_date": "2020",
            "geo_loc_name": "France",
            "host_disease": "NULL",
            "isolation_source": "blood",
            "number_drugs_resistant": "4",
            "number_amr_genes": "4",
            "number_core_amr_genes": "4",
            "AST_phenotypes": "oxacillin=R,erythromycin=R,clindamycin=R,gentamicin=R",
            "AMR_genotypes": "mecA,erm(C),ant(9)-Ia,tet(M)",
            "AMR_genotypes_core": "mecA,erm(C),ant(9)-Ia,tet(M)",
        },
        {
            "isolate_id": "MRSA_3",
            "collection_date": "2021",
            "geo_loc_name": "France",
            "host_disease": "NULL",
            "isolation_source": "wound",
            "number_drugs_resistant": "3",
            "number_amr_genes": "3",
            "number_core_amr_genes": "3",
            "AST_phenotypes": "oxacillin=R,erythromycin=R,clindamycin=S,gentamicin=S",
            "AMR_genotypes": "mecC,erm(C),tet(M)",
            "AMR_genotypes_core": "mecC,erm(C),tet(M)",
        },
        {
            "isolate_id": "MSSA_1",
            "collection_date": "2020",
            "geo_loc_name": "France",
            "host_disease": "NULL",
            "isolation_source": "blood",
            "number_drugs_resistant": "1",
            "number_amr_genes": "2",
            "number_core_amr_genes": "2",
            "AST_phenotypes": "oxacillin=S,erythromycin=R,clindamycin=S,gentamicin=S",
            "AMR_genotypes": "blaZ,erm(T)",
            "AMR_genotypes_core": "blaZ,erm(T)",
        },
        {
            "isolate_id": "MSSA_2",
            "collection_date": "2021",
            "geo_loc_name": "France",
            "host_disease": "NULL",
            "isolation_source": "wound",
            "number_drugs_resistant": "0",
            "number_amr_genes": "1",
            "number_core_amr_genes": "1",
            "AST_phenotypes": "oxacillin=S,erythromycin=S,clindamycin=S,gentamicin=S",
            "AMR_genotypes": "blaZ",
            "AMR_genotypes_core": "blaZ",
        },
        {
            "isolate_id": "MSSA_3",
            "collection_date": "2021",
            "geo_loc_name": "France",
            "host_disease": "NULL",
            "isolation_source": "urine",
            "number_drugs_resistant": "3",
            "number_amr_genes": "3",
            "number_core_amr_genes": "3",
            "AST_phenotypes": "oxacillin=S,erythromycin=R,clindamycin=R,gentamicin=R",
            "AMR_genotypes": "blaZ,erm(T),tet(K)",
            "AMR_genotypes_core": "blaZ,erm(T),tet(K)",
        },
    ]
    input_path = base / "demo.tsv"
    pd.DataFrame(rows).to_csv(input_path, sep="\t", index=False)

    config_dir = base / "config"
    config_dir.mkdir()
    (config_dir / "drug_classes.tsv").write_text(
        "drug\tclass\n"
        "oxacillin\tbeta-lactam\n"
        "cefoxitin\tbeta-lactam\n"
        "erythromycin\tmacrolide\n"
        "clindamycin\tlincosamide\n"
        "gentamicin\taminoglycoside\n"
        "tetracycline\ttetracycline\n",
        encoding="utf-8",
    )

    outdir = base / "results"
    code = analysis.main(
        [
            "--input",
            str(input_path),
            "--outdir",
            str(outdir),
            "--config-dir",
            str(config_dir),
            "--min-count",
            "1",
            "--min-prevalence",
            "0",
        ]
    )
    assert code == 0
    return outdir


def test_analysis_outputs_and_key_counts(demo_results: Path):
    for relative in [
        "summary.json",
        "tables/cohort_summary.csv",
        "tables/phenotype_concordance.csv",
        "tables/top_genes_mrsa.csv",
        "tables/top_genes_mdr.csv",
        "figures/fig00_pipeline.png",
        "figures/fig01_cohort.png",
        "figures/fig02_mrsa_genes.png",
        "figures/fig04_mdr_genes.png",
    ]:
        assert (demo_results / relative).exists(), relative

    summary = json.loads((demo_results / "summary.json").read_text(encoding="utf-8"))
    cohort = summary["cohort"]
    assert cohort["n_isolates"] == 6
    assert cohort["n_mecA"] == 2
    assert cohort["n_mecC"] == 1
    assert cohort["n_mrsa_genotype"] == 3
    assert cohort["n_ast"] == 6
    assert cohort["n_mrsa_phenotype"] == 3
    assert cohort["n_mssa_phenotype"] == 3
    assert cohort["n_mdr"] == 3  # 2 SARM + 1 MSSA
    assert cohort["n_mrsa_mdr"] == 2
    assert cohort["n_mssa_mdr"] == 1


def test_report_builds_at_most_four_pages(demo_results: Path, tmp_path: Path):
    group_config = tmp_path / "group.env"
    group_config.write_text(
        'GROUP_NAME="Groupe test"\n'
        'GROUP_MEMBERS="Test 1; Test 2"\n'
        'GROUP_COURSE="Module test"\n',
        encoding="utf-8",
    )
    pdf_path = tmp_path / "rapport.pdf"
    code = report.main(
        [
            "--results",
            str(demo_results),
            "--out",
            str(pdf_path),
            "--group-config",
            str(group_config),
        ]
    )
    assert code == 0
    assert pdf_path.exists()
    assert len(PdfReader(str(pdf_path)).pages) <= 4
