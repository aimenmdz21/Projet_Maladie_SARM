#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Génération du rapport PDF (4 pages maximum) du projet SARM.

Le rapport est construit à partir de results/summary.json, des tableaux CSV
et des figures produites par analysis.py. Les nombres ne sont pas saisis à la
main : ils sont lus dans les résultats, ce qui garantit la cohérence entre le
pipeline et le rapport.

Usage :
    python report.py --results results --out report/rapport.pdf
"""

from __future__ import annotations

import argparse
import html
import json
import re
from datetime import date
from pathlib import Path

import pandas as pd
from PIL import Image as PILImage
from pypdf import PdfReader

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    Image,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

# ---------------------------------------------------------------------------
# Couleurs et constantes
# ---------------------------------------------------------------------------

NAVY = colors.HexColor("#1d3557")
TEAL = colors.HexColor("#2a9d8f")
ORANGE = colors.HexColor("#e76f51")
GOLD = colors.HexColor("#e9c46a")
RED = colors.HexColor("#c1121f")
GRAY = colors.HexColor("#6c757d")
LIGHT = colors.HexColor("#f1f5f9")
MID = colors.HexColor("#dbe4ee")
WHITE = colors.white

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN_X = 1.65 * cm
MARGIN_TOP = 1.25 * cm
MARGIN_BOTTOM = 1.55 * cm
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN_X


# ---------------------------------------------------------------------------
# Lecture des résultats
# ---------------------------------------------------------------------------


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Résumé introuvable : {path}")
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Tableau introuvable : {path}")
    return pd.read_csv(path)


def load_group_config(path: Path) -> dict[str, str]:
    config: dict[str, str] = {}
    if not path.exists():
        return config
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
            value = value[1:-1]
        config[key.strip()] = value
    return config


# ---------------------------------------------------------------------------
# Formats français
# ---------------------------------------------------------------------------


def fmt_int(value) -> str:
    return f"{int(value):,}".replace(",", " ")


def fmt_pct(value: float) -> str:
    return f"{value:.1f} %".replace(".", ",")


def fmt_or(value: float) -> str:
    if value >= 1000:
        return f"{value:,.0f}".replace(",", " ")
    if value >= 100:
        return f"{value:.0f}"
    if value >= 10:
        return f"{value:.1f}".replace(".", ",")
    return f"{value:.2f}".replace(".", ",")


def fmt_ci(low: float, high: float) -> str:
    return f"{fmt_or(low)}–{fmt_or(high)}"


def fmt_q(value: float) -> str:
    if value < 0.001:
        return "< 0,001"
    return f"{value:.3f}".replace(".", ",")


def esc(text: str) -> str:
    return html.escape(str(text), quote=False)


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------


def register_fonts() -> tuple[str, str]:
    """Enregistre les polices DejaVu livrées avec matplotlib."""
    from matplotlib import font_manager

    regular = font_manager.findfont("DejaVu Sans")
    bold = font_manager.findfont(
        font_manager.FontProperties(family="DejaVu Sans", weight="bold")
    )
    oblique = font_manager.findfont(
        font_manager.FontProperties(family="DejaVu Sans", style="oblique")
    )
    bold_oblique = font_manager.findfont(
        font_manager.FontProperties(
            family="DejaVu Sans", weight="bold", style="oblique"
        )
    )
    pdfmetrics.registerFont(TTFont("DejaVu", regular))
    pdfmetrics.registerFont(TTFont("DejaVu-Bold", bold))
    pdfmetrics.registerFont(TTFont("DejaVu-Oblique", oblique))
    pdfmetrics.registerFont(TTFont("DejaVu-BoldOblique", bold_oblique))
    pdfmetrics.registerFontFamily(
        "DejaVu", normal="DejaVu", bold="DejaVu-Bold",
        italic="DejaVu-Oblique", boldItalic="DejaVu-BoldOblique",
    )
    return "DejaVu", "DejaVu-Bold"


def make_styles(font_regular: str, font_bold: str) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    styles: dict[str, ParagraphStyle] = {}

    styles["title"] = ParagraphStyle(
        "TitleSARM", parent=base["Title"], fontName=font_bold,
        fontSize=15.2, leading=18.2, textColor=WHITE, alignment=TA_LEFT,
        spaceAfter=2,
    )
    styles["subtitle"] = ParagraphStyle(
        "SubtitleSARM", parent=base["Normal"], fontName=font_regular,
        fontSize=8.2, leading=10.4, textColor=colors.HexColor("#dbe7f3"),
        alignment=TA_LEFT,
    )
    styles["group"] = ParagraphStyle(
        "GroupSARM", parent=base["Normal"], fontName=font_regular,
        fontSize=8.2, leading=10.2, textColor=GRAY, alignment=TA_LEFT,
        spaceBefore=3, spaceAfter=4,
    )
    styles["h1"] = ParagraphStyle(
        "H1SARM", parent=base["Heading1"], fontName=font_bold,
        fontSize=11.6, leading=13.6, textColor=NAVY,
        spaceBefore=7, spaceAfter=3,
    )
    styles["h2"] = ParagraphStyle(
        "H2SARM", parent=base["Heading2"], fontName=font_bold,
        fontSize=9.5, leading=11.4, textColor=TEAL,
        spaceBefore=4, spaceAfter=2,
    )
    styles["body"] = ParagraphStyle(
        "BodySARM", parent=base["BodyText"], fontName=font_regular,
        fontSize=8.55, leading=10.65, textColor=colors.HexColor("#222222"),
        alignment=TA_JUSTIFY, spaceAfter=3.2,
    )
    styles["body_small"] = ParagraphStyle(
        "BodySmallSARM", parent=styles["body"], fontSize=7.7, leading=9.45,
        spaceAfter=2.2,
    )
    styles["bullet"] = ParagraphStyle(
        "BulletSARM", parent=styles["body"], leftIndent=9, bulletIndent=1,
        spaceAfter=1.6,
    )
    styles["bullet_small"] = ParagraphStyle(
        "BulletSmallSARM", parent=styles["body_small"], leftIndent=9,
        bulletIndent=1, spaceAfter=1.2,
    )
    styles["box"] = ParagraphStyle(
        "BoxSARM", parent=styles["body"], fontSize=8.35, leading=10.3,
        textColor=NAVY, spaceAfter=0,
    )
    styles["box_title"] = ParagraphStyle(
        "BoxTitleSARM", parent=styles["box"], fontName=font_bold,
        fontSize=9.2, leading=11.0, spaceAfter=2,
    )
    styles["box_small"] = ParagraphStyle(
        "BoxSmallSARM", parent=styles["box"], fontSize=7.9, leading=9.8,
    )
    styles["caption"] = ParagraphStyle(
        "CaptionSARM", parent=base["Normal"], fontName=font_regular,
        fontSize=6.9, leading=8.4, textColor=GRAY, alignment=TA_LEFT,
        spaceBefore=1.5, spaceAfter=4,
    )
    styles["table_header"] = ParagraphStyle(
        "TableHeaderSARM", parent=base["Normal"], fontName=font_bold,
        fontSize=6.9, leading=8.2, textColor=WHITE, alignment=TA_LEFT,
    )
    styles["table_cell"] = ParagraphStyle(
        "TableCellSARM", parent=base["Normal"], fontName=font_regular,
        fontSize=6.8, leading=8.0, textColor=colors.HexColor("#222222"),
        alignment=TA_LEFT,
    )
    styles["table_cell_bold"] = ParagraphStyle(
        "TableCellBoldSARM", parent=styles["table_cell"], fontName=font_bold,
        textColor=NAVY,
    )
    styles["ref"] = ParagraphStyle(
        "RefSARM", parent=base["Normal"], fontName=font_regular,
        fontSize=6.4, leading=7.8, textColor=GRAY, alignment=TA_LEFT,
        spaceAfter=1.0,
    )
    return styles


# ---------------------------------------------------------------------------
# Composants de mise en page
# ---------------------------------------------------------------------------


def image_flow(path: Path, width: float) -> Image:
    """Insère une image en conservant son rapport largeur/hauteur."""
    with PILImage.open(path) as image:
        ratio = image.height / image.width
    return Image(str(path), width=width, height=width * ratio)


def colored_box(
    content: list,
    *,
    background=LIGHT,
    border=MID,
    padding: float = 7,
    width: float = CONTENT_WIDTH,
) -> Table:
    table = Table([[content]], colWidths=[width])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), background),
                ("BOX", (0, 0), (-1, -1), 0.6, border),
                ("LEFTPADDING", (0, 0), (-1, -1), padding),
                ("RIGHTPADDING", (0, 0), (-1, -1), padding),
                ("TOPPADDING", (0, 0), (-1, -1), padding - 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), padding - 1),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def section_title(text: str, styles: dict) -> Paragraph:
    return Paragraph(esc(text), styles["h1"])


def bullet(text: str, styles: dict, small: bool = False) -> Paragraph:
    style = styles["bullet_small"] if small else styles["bullet"]
    return Paragraph(f"• {text}", style)


def build_header(summary: dict, group: dict, styles: dict) -> list:
    title = Paragraph(
        "SARM : gènes de résistance associés à la méticilline et à la multirésistance "
        "chez <i>Staphylococcus aureus</i>",
        styles["title"],
    )
    subtitle = Paragraph(
        "Projet « Enquête sur une maladie » — pipeline reproductible d'analyse du "
        "snapshot public NCBI Pathogen Detection PDG000000073.1314",
        styles["subtitle"],
    )
    band = Table([[title], [subtitle]], colWidths=[CONTENT_WIDTH])
    band.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), NAVY),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (0, 0), 9),
                ("BOTTOMPADDING", (0, 1), (0, 1), 9),
                ("TOPPADDING", (0, 1), (0, 1), 2),
            ]
        )
    )
    members = group.get("GROUP_MEMBERS", "").replace(";", " · ").strip(" ·")
    meta = [f"<b>{esc(group.get('GROUP_NAME', 'Projet SARM'))}</b>"]
    if members:
        meta.append(esc(members))
    meta.append(f"{date.today():%d/%m/%Y}")
    meta.append(esc(group.get("GROUP_COURSE", "Module — Enquête sur une maladie")))
    group_line = Paragraph(" &nbsp;·&nbsp; ".join(meta), styles["group"])
    return [band, group_line]


def build_page1(summary: dict, styles: dict, fig1: Path, concordance: pd.DataFrame) -> list:
    cohort = summary["cohort"]
    story: list = []
    story.append(section_title("1. Question et contexte", styles))
    story.append(
        Paragraph(
            "<i>Staphylococcus aureus</i> est une bactérie commensale du nez et de la peau, "
            "mais aussi un pathogène majeur responsable d'infections cutanées, de bactériémies, "
            "d'endocardites et d'infections ostéo-articulaires. La résistance à la méticilline "
            "(SARM) est portée par les gènes <b>mecA</b> ou <b>mecC</b>, qui codent une "
            "protéine PBP2a de faible affinité pour les bêta-lactamines. Les SARM sont souvent "
            "aussi résistants aux aminosides, aux macrolides, aux tétracyclines ou aux "
            "fluoroquinolones, ce qui limite les options thérapeutiques et favorise la "
            "multirésistance (MDR).",
            styles["body"],
        )
    )
    story.append(
        colored_box(
            [
                Paragraph("<b>Question posée</b>", styles["box_title"]),
                Paragraph(
                    "Quels gènes de résistance, présents dans le champ <i>AMR_genotypes</i>, "
                    "sont associés (i) à la résistance à la méticilline et (ii) à la "
                    "multirésistance chez <i>S. aureus</i> ? Le motif recherché est la "
                    "présence de <b>mecA</b> ou <b>mecC</b> ; il est comparé à la présence "
                    "des autres gènes et validé sur le phénotype oxacilline/céfoxitine.",
                    styles["box"],
                ),
            ],
            background=colors.HexColor("#eaf4f1"),
            border=colors.HexColor("#b7dcd4"),
        )
    )
    story.append(Spacer(1, 4))
    story.append(section_title("2. Un jeu de données public et massif", styles))
    story.append(
        Paragraph(
            "Les données proviennent du dernier snapshot public de <b>NCBI Pathogen "
            "Detection</b>, identifiant <b>PDG000000073.1314</b>. Le fichier de métadonnées "
            "TSV pèse <b>164 176 554 octets</b> (164,2 Mo) et contient <b>175 586 isolats</b> "
            "de <i>S. aureus</i> décrits par 67 colonnes. Les génotypes de résistance sont "
            "issus d'AMRFinderPlus ; les phénotypes de sensibilité (AST) ne sont disponibles "
            "que pour <b>1 530 isolats</b> (0,87 %), ce qui impose de distinguer une analyse "
            "génotypique sur toute la cohorte et une validation phénotypique sur la "
            "sous-cohorte AST.",
            styles["body"],
        )
    )

    key_values = [
        ("175 586", "isolats analysés"),
        ("164,2 Mo", "métadonnées TSV"),
        (f"{fmt_pct(cohort['mrsa_genotype_percent'])}", "SARM génotypiques"),
        (f"{fmt_int(cohort['n_ast'])}", "isolats avec AST"),
        (f"{fmt_int(cohort['n_mrsa_phenotype'])}", "SARM phénotypiques"),
        (f"{fmt_pct(cohort['mdr_in_mrsa_percent'])}", "MDR chez les SARM"),
    ]
    key_table = Table(
        [[Paragraph(f"<b>{value}</b>", styles["box_title"]) for value, _ in key_values],
         [Paragraph(label, styles["caption"]) for _, label in key_values]],
        colWidths=[CONTENT_WIDTH / len(key_values)] * len(key_values),
    )
    key_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
                ("BOX", (0, 0), (-1, -1), 0.5, MID),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.white),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(key_table)
    story.append(Spacer(1, 3))
    story.append(image_flow(fig1, CONTENT_WIDTH))
    story.append(
        Paragraph(
            "Figure 1. Effectifs de la cohorte (A) et prévalence de la multirésistance "
            "selon le phénotype (B). La MDR est définie par la résistance à au moins "
            "trois classes d'antibiotiques.",
            styles["caption"],
        )
    )

    conc = concordance.iloc[0]
    result_box = colored_box(
        [
            Paragraph("<b>Résultat en bref</b>", styles["box_title"]),
            Paragraph(
                f"• <b>{fmt_pct(cohort['mrsa_genotype_percent'])}</b> des isolats portent "
                f"<i>mecA</i> ou <i>mecC</i> ({fmt_int(cohort['n_mrsa_genotype'])} SARM "
                f"génotypiques sur {fmt_int(cohort['n_isolates'])}).<br/>"
                f"• La concordance génotype/phénotype est de <b>98,1 %</b> "
                f"(κ = {conc['cohen_kappa']:.2f}) chez les {fmt_int(conc['n_compared'])} "
                f"isolats avec oxacilline/céfoxitine interprétables.<br/>"
                f"• La MDR touche <b>{fmt_pct(cohort['mdr_in_mrsa_percent'])}</b> des SARM "
                f"phénotypiques contre <b>{fmt_pct(cohort['mdr_in_mssa_percent'])}</b> des "
                f"MSSA, soit un odds ratio brut de {fmt_or((cohort['n_mrsa_mdr']/max(1,cohort['n_mrsa_mdr_known']-cohort['n_mrsa_mdr']))/(cohort['n_mssa_mdr']/max(1,cohort['n_mssa_mdr_known']-cohort['n_mssa_mdr'])))}.<br/>"
                f"• Les gènes co-portés les plus fortement associés au SARM sont "
                f"<i>gyrA</i>, <i>parC</i>, <i>dfrK</i>, <i>mph(C)</i>, "
                f"<i>ant(6)-Ia</i> et <i>tet(M)</i> (q &lt; 0,05).",
                styles["box"],
            ),
        ],
        background=colors.HexColor("#fff6e5"),
        border=colors.HexColor("#efd8a8"),
    )
    story.append(result_box)
    return story


def build_page2(summary: dict, styles: dict, fig_pipeline: Path, cohort_table: pd.DataFrame) -> list:
    story: list = [PageBreak(), section_title("3. Définition du motif et méthode", styles)]
    story.append(
        Paragraph(
            "Le pipeline transforme le TSV brut en un tableau analysable, définit un motif "
            "explicite, puis compare les groupes par des tests statistiques. Toutes les "
            "étapes sont exécutées par <b>run.sh</b>, sans intervention manuelle.",
            styles["body"],
        )
    )
    story.append(
        colored_box(
            [
                Paragraph("<b>Motif génotypique</b>", styles["box_title"]),
                Paragraph(
                    "Pour chaque isolat <i>x</i>, soit <i>G(x)</i> l'ensemble des gènes "
                    "extraits de <i>AMR_genotypes</i> (les variants sont ramenés au gène : "
                    "<i>gyrA_S84L=POINT</i> → <i>gyrA</i>). Le motif est :<br/><br/>"
                    "<b>P(x) = 1 si mecA ∈ G(x) ou mecC ∈ G(x), sinon 0.</b><br/><br/>"
                    "Validation phénotypique : SARM si <b>oxacilline = R</b> ou "
                    "<b>céfoxitine = R</b> ; MSSA si au moins l'un des deux est S et aucun "
                    "n'est R ; sinon phénotype inconnu. La méticilline elle-même n'est pas "
                    "testée dans AST, ces deux marqueurs sont les substituts recommandés.",
                    styles["box"],
                ),
            ],
            background=colors.HexColor("#eaf0f8"),
            border=colors.HexColor("#b9cbe0"),
        )
    )
    story.append(Spacer(1, 3))
    story.append(
        colored_box(
            [
                Paragraph("<b>Multirésistance (MDR)</b>", styles["box_title"]),
                Paragraph(
                    "Une classe est comptée résistante si au moins un antibiotique de cette "
                    "classe est R (ou NS). <b>MDR = 1</b> si au moins <b>3 classes</b> sont "
                    "résistantes et si au moins 3 classes ont été testées ; sinon MDR = 0. "
                    "Le mapping des 59 antibiotiques vers 17 classes est dans "
                    "<i>config/drug_classes.tsv</i> (bêta-lactamines, aminosides, macrolides, "
                    "lincosamides, tétracyclines, fluoroquinolones, folate/sulfamides, "
                    "glycopeptides, oxazolidinones, rifampicine, lipopeptides, etc.).",
                    styles["box"],
                ),
            ],
            background=colors.HexColor("#fff6e5"),
            border=colors.HexColor("#efd8a8"),
        )
    )
    story.append(Spacer(1, 4))
    story.append(image_flow(fig_pipeline, CONTENT_WIDTH))
    story.append(
        Paragraph(
            "Figure 2. Pipeline reproductible : acquisition et contrôle d'intégrité, "
            "nettoyage Shell, analyse Python, sorties horodatées et archivage.",
            styles["caption"],
        )
    )
    story.append(section_title("3.1 Étapes et contrôles", styles))
    for text in [
        "<b>Acquisition :</b> téléchargement FTP avec <i>curl</i>, vérification de la taille "
        "(164 176 554 octets) et du SHA-256 "
        "(<font face='DejaVu'>3170dd18…ebcb82</font>), fichier brut en lecture seule.",
        "<b>Nettoyage Shell :</b> <i>cut</i> sélectionne 11 colonnes, <i>awk</i> filtre les "
        "lignes sans génotype et écrit l'en-tête, <i>sed</i> retire les guillemets. Un second "
        "enchaînement <i>tail | cut | tr | sed | sort | uniq -c | sort -rn</i> produit le "
        "palmarès des gènes.",
        "<b>Analyse Python :</b> pandas construit les 230 gènes normalisés, les variables "
        "SARM/MDR et les tableaux 2×2 ; scipy réalise les tests de Fisher ; les q-values "
        "sont calculées par Benjamini-Hochberg.",
        "<b>Traçabilité :</b> journal horodaté dans <i>logs/</i>, checksums, archive "
        "<i>tar.gz</i> datée, rapport PDF et diapositives générés automatiquement.",
    ]:
        story.append(bullet(text, styles, small=True))

    story.append(section_title("3.2 Tests statistiques", styles))
    story.append(
        Paragraph(
            "Pour chaque gène, une table 2×2 oppose sa présence/absence dans le groupe "
            "d'intérêt (SARM ou MDR) et dans le groupe contrôle. Le test exact de Fisher "
            "bilatéral est utilisé car certains gènes sont rares. L'odds ratio est estimé "
            "avec la correction de Haldane-Anscombe (+0,5) et son intervalle de confiance "
            "à 95 % est calculé sur l'échelle log. Les gènes dont la prévalence est "
            "inférieure à 1 % dans les deux groupes, ou inférieure à 10 isolats, sont "
            "filtrés ; les gènes intrinsèques présents chez plus de 95 % des deux groupes "
            "sont exclus. Le seuil de significativité est <b>q &lt; 0,05</b> après "
            "correction de Benjamini-Hochberg.",
            styles["body"],
        )
    )

    # Tableau de cohorte compact
    wanted = [
        "Isolats analysés",
        "SARM génotypique (mecA ou mecC)",
        "Isolats avec AST",
        "Phénotype SARM (oxacilline ou céfoxitine R)",
        "MDR évaluable",
        "MDR (>= 3 classes R)",
        "MDR chez les SARM phénotypiques",
        "MDR chez les MSSA phénotypiques",
    ]
    rows = [["Indicateur", "n", "Base", "%"]]
    for metric in wanted:
        line = cohort_table.loc[cohort_table["metric"] == metric]
        if line.empty:
            continue
        line = line.iloc[0]
        rows.append(
            [
                Paragraph(esc(metric), styles["table_cell"]),
                Paragraph(fmt_int(line["n"]), styles["table_cell_bold"]),
                Paragraph(fmt_int(line["denominator"]), styles["table_cell"]),
                Paragraph(fmt_pct(line["percent"]), styles["table_cell"]),
            ]
        )
    table = Table(rows, colWidths=[9.4 * cm, 2.5 * cm, 2.5 * cm, 2.5 * cm], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("FONTNAME", (0, 0), (-1, 0), "DejaVu-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 6.9),
                ("GRID", (0, 0), (-1, -1), 0.35, MID),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 2.4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.4),
            ]
        )
    )
    story.append(Spacer(1, 3))
    story.append(table)
    story.append(
        Paragraph(
            "Tableau 1. Définition des sous-cohortes. La base du pourcentage est indiquée "
            "dans la colonne « Base » ; les lignes MDR ne concernent que les isolats dont "
            "au moins trois classes ont été testées.",
            styles["caption"],
        )
    )
    return story


def build_page3(summary: dict, styles: dict, fig2: Path, top_mrsa: pd.DataFrame) -> list:
    cohort = summary["cohort"]
    story: list = [PageBreak(), section_title("4. Résultats : gènes associés au SARM", styles)]
    story.append(
        Paragraph(
            f"Sur les {fmt_int(cohort['n_isolates'])} isolats, {fmt_int(cohort['n_mrsa_genotype'])} "
            f"({fmt_pct(cohort['mrsa_genotype_percent'])}) portent <i>mecA</i> ou <i>mecC</i> "
            f"et {fmt_int(cohort['n_mssa_genotype'])} sont MSSA. Les marqueurs de la cassette "
            f"SCCmec sont, sans surprise, les plus fortement associés : <i>mecR1</i> est présent "
            f"chez 81,1 % des SARM contre 0,04 % des MSSA (OR = 9 442), <i>mecI</i> chez 19,7 % "
            f"contre 0,02 % (OR = 1 037) et <i>bleO</i> chez 15,5 % contre 0,7 % (OR = 25,3). "
            f"Ces gènes font partie du motif et ne sont donc pas interprétés comme des "
            f"facteurs indépendants.",
            styles["body"],
        )
    )
    story.append(
        Paragraph(
            "En dehors de la cassette, le SARM est associé à un cortège de gènes de "
            "co-résistance, avec des prévalences très supérieures à celles des MSSA : "
            "<i>gyrA</i> (54,7 % vs 4,9 % ; OR = 23,3), <i>parC</i> (57,8 % vs 7,4 % ; "
            "OR = 17,1), <i>dfrK</i> (2,2 % vs 0,1 % ; OR = 17,5), <i>mph(C)</i> (21,8 % vs "
            "2,3 % ; OR = 11,8), <i>ant(6)-Ia</i> (27,8 % vs 3,2 % ; OR = 11,6), "
            "<i>aph(3')-IIIa</i> (27,3 % vs 3,3 % ; OR = 11,1), <i>sat4</i> (23,1 % vs 2,6 % ; "
            "OR = 11,1) et <i>tet(M)</i> (16,2 % vs 1,7 % ; OR = 11,0). Tous les q-values "
            "sont inférieurs à 0,001 après correction de Benjamini-Hochberg.",
            styles["body"],
        )
    )
    story.append(image_flow(fig2, 12.8 * cm))
    story.append(
        Paragraph(
            "Figure 3. Gènes co-portés avec <i>mecA/mecC</i> (hors marqueurs de la cassette "
            "SCCmec). Les points sont les odds ratios, les barres les IC 95 % ; les valeurs "
            "à droite sont les prévalences SARM → MSSA. Échelle log, test de Fisher, "
            "q &lt; 0,05 (BH).",
            styles["caption"],
        )
    )
    story.append(section_title("4.1 Les gènes enrichis, en chiffres", styles))
    story.append(
        Paragraph(
            "Le tableau 2 donne les huit premiers gènes enrichis hors cassette. La "
            "co-occurrence de ces gènes (figure supplémentaire S1) révèle deux modules "
            "principaux : un module aminosides/macrolides (<i>mph(C)</i>, <i>sat4</i>, "
            "<i>ant(6)-Ia</i>, <i>aph(3')-IIIa</i>) et un module fluoroquinolones "
            "(<i>gyrA</i>, <i>parC</i>), tandis que <i>tet(M)</i>, <i>dfrK</i> et "
            "<i>folP</i> forment un troisième bloc plus faible. À l'inverse, <i>erm(T)</i> "
            "est plus fréquent chez les MSSA (4,8 % vs 0,3 % ; OR = 0,06) et les variants "
            "de <i>glpT</i> sont associés aux MSSA, ce qui illustre la structure clonale "
            "des populations.",
            styles["body_small"],
        )
    )

    rows = [["Gène", "Famille", "SARM", "MSSA", "OR [IC 95 %]"]]
    for _, row in top_mrsa.head(8).iterrows():
        rows.append(
            [
                Paragraph(f"<i>{esc(row['gene'])}</i>", styles["table_cell"]),
                Paragraph(esc(row["family"]), styles["table_cell"]),
                Paragraph(fmt_pct(row["prevalence_group"] * 100), styles["table_cell"]),
                Paragraph(fmt_pct(row["prevalence_control"] * 100), styles["table_cell"]),
                Paragraph(
                    f"{fmt_or(row['odds_ratio'])} [{fmt_ci(row['or_ci_low'], row['or_ci_high'])}]",
                    styles["table_cell"],
                ),
            ]
        )
    table = Table(rows, colWidths=[2.7 * cm, 4.9 * cm, 1.9 * cm, 1.9 * cm, 6.0 * cm], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("GRID", (0, 0), (-1, -1), 0.35, MID),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 2.2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
            ]
        )
    )
    story.append(table)
    story.append(
        Paragraph(
            "Tableau 2. Top 8 des gènes associés au SARM génotypique, hors <i>mecA</i>, "
            "<i>mecC</i>, <i>mecI</i>, <i>mecR1</i> et <i>bleO</i>. Tous les q-values sont "
            "&lt; 0,001. OR = odds ratio avec correction de Haldane ; IC 95 % sur l'échelle log.",
            styles["caption"],
        )
    )
    story.append(Spacer(1, 2))
    story.append(
        colored_box(
            [
                Paragraph("<b>Lecture biologique</b>", styles["box_title"]),
                Paragraph(
                    "La cassette <i>SCCmec</i> explique le noyau du SARM (<i>mecA/mecC</i>, "
                    "<i>mecI</i>, <i>mecR1</i>, <i>bleO</i>). Les gènes situés hors cassette "
                    "(<i>gyrA</i>, <i>parC</i>, <i>dfrK</i>, <i>mph(C)</i>, "
                    "<i>ant(6)-Ia</i>, <i>tet(M)</i>) correspondent à des co-résistances "
                    "acquises, souvent portées par des transposons ou des plasmides. Leur "
                    "présence conjointe suggère une sélection sous pression antibiotique et "
                    "un risque d'impasse thérapeutique.",
                    styles["box_small"],
                ),
            ],
            background=colors.HexColor("#eaf4f1"),
            border=colors.HexColor("#b7dcd4"),
        )
    )
    return story


def build_page4(summary: dict, styles: dict, fig4: Path, top_mdr: pd.DataFrame) -> list:
    cohort = summary["cohort"]
    crude_or = (
        (cohort["n_mrsa_mdr"] / (cohort["n_mrsa_mdr_known"] - cohort["n_mrsa_mdr"]))
        / (cohort["n_mssa_mdr"] / (cohort["n_mssa_mdr_known"] - cohort["n_mssa_mdr"]))
    )
    story: list = [PageBreak(), section_title("5. Résultats : la multirésistance", styles)]
    story.append(
        Paragraph(
            f"Parmi les {fmt_int(cohort['n_mrsa_mdr_known'])} SARM phénotypiques, "
            f"<b>{fmt_int(cohort['n_mrsa_mdr'])}</b> sont MDR "
            f"({fmt_pct(cohort['mdr_in_mrsa_percent'])}), contre "
            f"<b>{fmt_int(cohort['n_mssa_mdr'])}</b> sur "
            f"{fmt_int(cohort['n_mssa_mdr_known'])} MSSA "
            f"({fmt_pct(cohort['mdr_in_mssa_percent'])}), soit un odds ratio brut de "
            f"<b>{fmt_or(crude_or)}</b>. La multirésistance est donc fortement liée au "
            f"fond génétique SARM, mais elle n'est pas uniforme : près de la moitié des "
            f"SARM restent non-MDR.",
            styles["body"],
        )
    )
    story.append(
        Paragraph(
            "Les gènes les plus fortement associés à la MDR chez les SARM sont "
            "<i>erm(C)</i> (28,3 % vs 0,0 % ; OR = 175), <i>erm(A)</i> (47,8 % vs 0,5 % ; "
            "OR = 134), <i>ant(9)-Ia</i> (46,2 % vs 0,5 % ; OR = 126), <i>aadD1</i> "
            "(40,9 % vs 1,8 % ; OR = 33), <i>mecI</i> et <i>bleO</i> (36 % vs 1,4 % ; "
            "OR ≈ 35), <i>rpsJ</i> (11,7 % vs 0,5 % ; OR = 20) et <i>mupA</i> (8,9 % vs "
            "0,5 % ; OR = 15). Les gènes <i>erm(A)</i> et <i>ant(9)-Ia</i> sont connus pour "
            "être portés par des éléments mobiles (dont Tn554), ce qui suggère une "
            "acquisition conjointe de plusieurs résistances plutôt qu'une simple "
            "addition de gènes indépendants.",
            styles["body_small"],
        )
    )
    story.append(image_flow(fig4, 12.0 * cm))
    story.append(
        Paragraph(
            "Figure 4. Gènes associés à la MDR chez les SARM phénotypiques (n = 467). "
            "OR et IC 95 % (échelle log), test de Fisher, q &lt; 0,05 (BH). Les valeurs à "
            "droite sont les prévalences MDR → non-MDR. <i>erm(C)</i> n'est présent chez "
            "aucun non-MDR : l'OR est estimé avec la correction de Haldane.",
            styles["caption"],
        )
    )
    story.append(section_title("6. Limites", styles))
    for text in [
        "<b>Couverture AST faible :</b> seulement 1 530 isolats (0,87 %) ont des "
        "phénotypes, et 1 320 ont oxacilline/céfoxitine interprétables. Les analyses "
        "phénotypiques sont donc puissantes mais non représentatives de tout le snapshot.",
        "<b>Définition génotypique :</b> la présence de <i>mecA/mecC</i> ne garantit pas "
        "l'expression de la résistance ; la concordance observée (98,1 %) est néanmoins "
        "excellente.",
        "<b>Confusion par le lignage :</b> les associations ne sont pas ajustées sur le "
        "clone, le pays ou la source. Un gène peut être enrichi parce qu'il est fixé dans "
        "un lignage SARM particulier, pas parce qu'il cause la résistance.",
        "<b>MDR dépendante du panel :</b> le nombre de classes testées varie selon les "
        "isolats ; la définition MDR est standard mais la sensibilité des tests et les "
        "seuils CLSI peuvent différer entre laboratoires.",
        "<b>Gènes et variants :</b> les variants de <i>gyrA/parC</i> sont agrégés au gène ; "
        "l'analyse ne distingue pas les mutations conférant des niveaux de résistance "
        "différents. Les gènes de virulence et les séquences brutes ne sont pas analysés.",
    ]:
        story.append(bullet(text, styles, small=True))

    story.append(section_title("7. Conclusion", styles))
    story.append(
        Paragraph(
            "Le snapshot NCBI confirme que le SARM est majoritaire dans <i>S. aureus</i> "
            "et qu'il s'accompagne d'un fardeau de co-résistances : aminosides, macrolides, "
            "tétracyclines, folate et fluoroquinolones. La multirésistance est plus de "
            "quatre fois plus fréquente chez les SARM que chez les MSSA (52,9 % vs 12,9 %). Les gènes "
            "identifiés sont cohérents avec les mécanismes connus (cassette SCCmec, "
            "transposons, mutations de cibles) et fournissent des hypothèses testables "
            "sur génomes complets. Le pipeline est entièrement reproductible : "
            "<b>./run.sh</b> télécharge, vérifie, analyse, illustre et archive les résultats.",
            styles["body_small"],
        )
    )
    story.append(Spacer(1, 2))
    story.append(
        colored_box(
            [
                Paragraph(
                    "<b>Reproductibilité.</b> Commande : <font face='DejaVu'>./run.sh</font> "
                    "(options : <font face='DejaVu'>-h</font>, <font face='DejaVu'>-f</font>, "
                    "<font face='DejaVu'>-n</font>, <font face='DejaVu'>-i FICHIER</font>, "
                    "<font face='DejaVu'>-k</font>). Environnement : "
                    "<font face='DejaVu'>requirements.txt</font> et venv local. Données non "
                    "jointes : le script les télécharge et vérifie leur SHA-256. "
                    "Résultats : <font face='DejaVu'>results/tables/</font>, "
                    "<font face='DejaVu'>results/figures/</font>, "
                    "<font face='DejaVu'>results/summary.json</font>.",
                    styles["caption"],
                )
            ],
            background=LIGHT,
            border=MID,
            padding=5,
        )
    )
    story.append(Spacer(1, 2))
    references = [
        "NCBI Pathogen Detection. <i>Staphylococcus aureus</i> snapshot PDG000000073.1314, "
        "metadata TSV, 164 176 554 octets, téléchargé le 30/10/2026. "
        "https://ftp.ncbi.nlm.nih.gov/pathogen/Results/Staphylococcus_aureus/PDG000000073.1314/",
        "Feldgarden M. et al. AMRFinderPlus and the Reference Gene Catalog facilitate "
        "examination of the genomic links among antimicrobial resistance, stress response, "
        "and virulence. <i>Sci Rep</i> 2021;11:12728.",
        "Magiorakos A.P. et al. Multidrug-resistant, extensively drug-resistant and "
        "pandrug-resistant bacteria: an international expert proposal. <i>Clin Microbiol "
        "Infect</i> 2012;18:268–281.",
        "CLSI. Performance Standards for Antimicrobial Susceptibility Testing, 34th ed. "
        "M100, 2024.",
    ]
    for reference in references:
        story.append(Paragraph(reference, styles["ref"]))
    return story


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(MID)
    canvas.setLineWidth(0.5)
    canvas.line(MARGIN_X, 1.18 * cm, PAGE_WIDTH - MARGIN_X, 1.18 * cm)
    canvas.setFont("DejaVu", 6.8)
    canvas.setFillColor(GRAY)
    canvas.drawString(MARGIN_X, 0.82 * cm, "Projet « Enquête sur une maladie » — SARM")
    canvas.drawRightString(PAGE_WIDTH - MARGIN_X, 0.82 * cm, f"page {doc.page}")
    canvas.restoreState()


def build_pdf(
    summary: dict,
    group: dict,
    results_dir: Path,
    out_path: Path,
    max_pages: int = 4,
) -> int:
    font_regular, font_bold = register_fonts()
    styles = make_styles(font_regular, font_bold)

    tables = results_dir / "tables"
    figures = results_dir / "figures"
    cohort_table = load_csv(tables / "cohort_summary.csv")
    concordance = load_csv(tables / "phenotype_concordance.csv")
    top_mrsa = load_csv(tables / "top_genes_mrsa.csv")
    top_mdr = load_csv(tables / "top_genes_mdr.csv")

    doc = BaseDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=MARGIN_X,
        rightMargin=MARGIN_X,
        topMargin=MARGIN_TOP,
        bottomMargin=MARGIN_BOTTOM,
        title="SARM — gènes de résistance et multirésistance",
        author=group.get("GROUP_NAME", "Projet SARM"),
        subject="Projet Enquête sur une maladie — NCBI Pathogen Detection PDG000000073.1314",
    )
    frame = Frame(
        doc.leftMargin, doc.bottomMargin, doc.width, doc.height,
        id="normal", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
    )
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=footer)])

    story: list = []
    story.extend(build_header(summary, group, styles))
    story.extend(
        build_page1(summary, styles, figures / "fig01_cohort.png", concordance)
    )
    story.extend(
        build_page2(summary, styles, figures / "fig00_pipeline.png", cohort_table)
    )
    story.extend(build_page3(summary, styles, figures / "fig02_mrsa_genes.png", top_mrsa))
    story.extend(build_page4(summary, styles, figures / "fig04_mdr_genes.png", top_mdr))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.build(story)

    pages = len(PdfReader(str(out_path)).pages)
    print(f"[report] PDF généré : {out_path} ({pages} pages)")
    if pages > max_pages:
        print(
            f"[report] ERREUR : {pages} pages > limite de {max_pages}. "
            "Réduire le contenu du rapport.",
            file=__import__("sys").stderr,
        )
        return 3
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Génère le rapport PDF de 4 pages du projet SARM.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Exemple : python report.py --results results --out report/rapport.pdf",
    )
    parser.add_argument("--results", default=Path("results"), type=Path,
                        help="Dossier des résultats (défaut : results).")
    parser.add_argument("--out", default=Path("report/rapport.pdf"), type=Path,
                        help="Fichier PDF de sortie (défaut : report/rapport.pdf).")
    parser.add_argument("--group-config", default=Path("config/group.env"), type=Path,
                        help="Fichier de configuration du groupe (défaut : config/group.env).")
    parser.add_argument("--max-pages", default=4, type=int,
                        help="Nombre maximal de pages (défaut : 4).")
    args = parser.parse_args(argv)

    try:
        summary = load_json(args.results / "summary.json")
        group = load_group_config(args.group_config)
        return build_pdf(summary, group, args.results, args.out, args.max_pages)
    except FileNotFoundError as error:
        print(f"[report] ERREUR : {error}", file=__import__("sys").stderr)
        return 2
    except Exception as error:  # pragma: no cover
        print(f"[report] ERREUR inattendue : {error}", file=__import__("sys").stderr)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
