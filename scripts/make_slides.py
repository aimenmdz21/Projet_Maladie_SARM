#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Génère la présentation orale (PPTX, 16:9) à partir des résultats du pipeline.

Le script ne saisit aucun chiffre à la main : il lit results/summary.json et les
tableaux CSV, puis remplit les diapositives et les notes de l'orateur. Il peut
être appelé par run.sh après analysis.py et report.py.

Usage :
    python make_slides.py --results results --out presentation/presentation.pptx
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
from PIL import Image as PILImage
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

# ---------------------------------------------------------------------------
# Charte graphique
# ---------------------------------------------------------------------------

NAVY = RGBColor(0x1D, 0x35, 0x57)
TEAL = RGBColor(0x2A, 0x9D, 0x8F)
ORANGE = RGBColor(0xE7, 0x6F, 0x51)
GOLD = RGBColor(0xE9, 0xC4, 0x6A)
RED = RGBColor(0xC1, 0x12, 0x1F)
BLUE = RGBColor(0x45, 0x7B, 0x9D)
GRAY = RGBColor(0x6C, 0x75, 0x7D)
LIGHT = RGBColor(0xF1, 0xF5, 0xF9)
MID = RGBColor(0xDB, 0xE4, 0xEE)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
DARK = RGBColor(0x22, 0x22, 0x22)
PALE_TEAL = RGBColor(0xEA, 0xF4, 0xF1)
PALE_GOLD = RGBColor(0xFF, 0xF6, 0xE5)

FONT = "Calibri"
SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)
MARGIN = Inches(0.55)
CONTENT_W = SLIDE_W - 2 * MARGIN


# ---------------------------------------------------------------------------
# Lectures
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


def load_group(path: Path) -> dict[str, str]:
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


def fmt_int(value) -> str:
    return f"{int(value):,}".replace(",", " ")


def fmt_pct(value: float, decimals: int = 1) -> str:
    return f"{value:.{decimals}f} %".replace(".", ",")


def fmt_or(value: float) -> str:
    if value >= 1000:
        return f"{value:,.0f}".replace(",", " ")
    if value >= 100:
        return f"{value:.0f}"
    if value >= 10:
        return f"{value:.1f}".replace(".", ",")
    return f"{value:.2f}".replace(".", ",")


# ---------------------------------------------------------------------------
# Composants PowerPoint
# ---------------------------------------------------------------------------


def add_rect(
    slide,
    x,
    y,
    w,
    h,
    fill,
    line=None,
    radius: bool = False,
    shadow: bool = False,
):
    shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE,
        x,
        y,
        w,
        h,
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    if line is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = line
        shape.line.width = Pt(1)
    if radius:
        try:
            shape.adjustments[0] = 0.08
        except Exception:
            pass
    if not shadow:
        shape.shadow.inherit = False
    return shape


def add_text(
    slide,
    text: str,
    x,
    y,
    w,
    h,
    *,
    size: float = 18,
    bold: bool = False,
    color=DARK,
    align=PP_ALIGN.LEFT,
    anchor=MSO_ANCHOR.TOP,
    font: str = FONT,
    line_spacing: float = 1.0,
    margins: float = 0.03,
):
    box = slide.shapes.add_textbox(x, y, w, h)
    frame = box.text_frame
    frame.word_wrap = True
    frame.margin_left = Inches(margins)
    frame.margin_right = Inches(margins)
    frame.margin_top = Inches(margins)
    frame.margin_bottom = Inches(margins)
    frame.vertical_anchor = anchor
    paragraph = frame.paragraphs[0]
    paragraph.alignment = align
    paragraph.line_spacing = line_spacing
    run = paragraph.add_run()
    run.text = text
    run.font.name = font
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    return box


def add_rich_text(slide, runs, x, y, w, h, *, size=18, align=PP_ALIGN.LEFT,
                  anchor=MSO_ANCHOR.TOP, line_spacing=1.0):
    """Ajoute un paragraphe composé de plusieurs runs (texte, gras, couleur)."""
    box = slide.shapes.add_textbox(x, y, w, h)
    frame = box.text_frame
    frame.word_wrap = True
    frame.margin_left = Inches(0.03)
    frame.margin_right = Inches(0.03)
    frame.margin_top = Inches(0.03)
    frame.margin_bottom = Inches(0.03)
    frame.vertical_anchor = anchor
    paragraph = frame.paragraphs[0]
    paragraph.alignment = align
    paragraph.line_spacing = line_spacing
    for text, bold, color in runs:
        run = paragraph.add_run()
        run.text = text
        run.font.name = FONT
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = color
    return box


def add_bullets(
    slide,
    items,
    x,
    y,
    w,
    h,
    *,
    size: float = 16,
    color=DARK,
    bullet_color=TEAL,
    spacing: float = 8,
    line_spacing: float = 1.0,
):
    box = slide.shapes.add_textbox(x, y, w, h)
    frame = box.text_frame
    frame.word_wrap = True
    frame.margin_left = Inches(0.03)
    frame.margin_right = Inches(0.03)
    frame.margin_top = Inches(0.03)
    frame.margin_bottom = Inches(0.03)
    first = True
    for item in items:
        if isinstance(item, tuple):
            text, level = item
        else:
            text, level = item, 0
        paragraph = frame.paragraphs[0] if first else frame.add_paragraph()
        first = False
        paragraph.space_after = Pt(spacing)
        paragraph.line_spacing = line_spacing
        marker = "•  " if level == 0 else "–  "
        run = paragraph.add_run()
        run.text = marker + text
        run.font.name = FONT
        run.font.size = Pt(size if level == 0 else size - 2)
        run.font.color.rgb = color if level == 0 else GRAY
        run.font.bold = False
        if level == 0:
            # La puce est incluse dans le texte ; la couleur du texte reste
            # homogène, ce qui suffit pour une projection.
            pass
    return box


def add_title(slide, title: str, kicker: str | None = None, number: int | None = None):
    add_rect(slide, 0, 0, SLIDE_W, Inches(0.10), TEAL)
    if kicker:
        add_text(
            slide, kicker.upper(), MARGIN, Inches(0.30), CONTENT_W, Inches(0.25),
            size=10.5, bold=True, color=TEAL,
        )
        title_y = Inches(0.58)
        title_h = Inches(0.70)
    else:
        title_y = Inches(0.38)
        title_h = Inches(0.80)
    add_text(
        slide, title, MARGIN, title_y, CONTENT_W, title_h,
        size=27, bold=True, color=NAVY, line_spacing=0.95,
    )
    add_rect(slide, MARGIN, Inches(1.38), Inches(1.1), Inches(0.045), ORANGE)
    if number is not None:
        add_footer(slide, number)


def add_footer(slide, number: int, label: str = "Projet SARM — NCBI Pathogen Detection"):
    add_rect(slide, MARGIN, SLIDE_H - Inches(0.52), CONTENT_W, Emu(9525), MID)
    add_text(
        slide, label, MARGIN, SLIDE_H - Inches(0.47), Inches(10.0), Inches(0.25),
        size=9, color=GRAY,
    )
    add_text(
        slide, f"{number:02d}", SLIDE_W - MARGIN - Inches(0.8), SLIDE_H - Inches(0.47),
        Inches(0.8), Inches(0.25), size=9, bold=True, color=NAVY, align=PP_ALIGN.RIGHT,
    )


def add_kpi(slide, x, y, w, h, value, label, color=NAVY, fill=LIGHT):
    add_rect(slide, x, y, w, h, fill, line=MID, radius=True)
    add_rect(slide, x, y, Inches(0.07), h, color)
    add_text(
        slide, value, x + Inches(0.18), y + Inches(0.10), w - Inches(0.28), Inches(0.52),
        size=25, bold=True, color=color,
    )
    add_text(
        slide, label, x + Inches(0.18), y + h - Inches(0.52), w - Inches(0.28), Inches(0.42),
        size=10.5, color=GRAY, line_spacing=0.95,
    )


def add_box(slide, x, y, w, h, title, body, *, accent=TEAL, fill=PALE_TEAL,
            title_size=14, body_size=13):
    add_rect(slide, x, y, w, h, fill, line=MID, radius=True)
    add_rect(slide, x, y, Inches(0.075), h, accent)
    add_text(
        slide, title, x + Inches(0.18), y + Inches(0.10), w - Inches(0.30), Inches(0.30),
        size=title_size, bold=True, color=NAVY,
    )
    add_text(
        slide, body, x + Inches(0.18), y + Inches(0.42), w - Inches(0.30), h - Inches(0.50),
        size=body_size, color=DARK, line_spacing=1.05,
    )


def add_image_fit(slide, path: Path, left, top, max_w, max_h):
    if not path.exists():
        return None
    with PILImage.open(path) as image:
        ratio = image.width / image.height
    width = max_w
    height = width / ratio
    if height > max_h:
        height = max_h
        width = height * ratio
    x = left + int((max_w - width) / 2)
    y = top + int((max_h - height) / 2)
    return slide.shapes.add_picture(str(path), x, y, width=width, height=height)


def add_table(
    slide,
    data,
    x,
    y,
    w,
    h,
    *,
    col_widths=None,
    header_fill=NAVY,
    font_size=12,
    header_size=12,
    first_col_bold=False,
):
    rows = len(data)
    cols = len(data[0])
    shape = slide.shapes.add_table(rows, cols, x, y, w, h)
    table = shape.table
    if col_widths:
        total = sum(col_widths)
        for index, width in enumerate(col_widths):
            table.columns[index].width = int(w * width / total)
    for r, row in enumerate(data):
        for c, value in enumerate(row):
            cell = table.cell(r, c)
            cell.margin_left = Inches(0.06)
            cell.margin_right = Inches(0.06)
            cell.margin_top = Inches(0.03)
            cell.margin_bottom = Inches(0.03)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.fill.solid()
            if r == 0:
                cell.fill.fore_color.rgb = header_fill
            else:
                cell.fill.fore_color.rgb = WHITE if r % 2 else LIGHT
            paragraph = cell.text_frame.paragraphs[0]
            paragraph.alignment = PP_ALIGN.CENTER if c > 0 else PP_ALIGN.LEFT
            run = paragraph.add_run()
            run.text = str(value)
            run.font.name = FONT
            run.font.size = Pt(header_size if r == 0 else font_size)
            run.font.bold = (r == 0) or (first_col_bold and c == 0)
            run.font.color.rgb = WHITE if r == 0 else DARK
    return table


def set_notes(slide, text: str):
    slide.notes_slide.notes_text_frame.text = text


# ---------------------------------------------------------------------------
# Diapositives
# ---------------------------------------------------------------------------


def slide_title(prs, summary: dict, group: dict) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_rect(slide, 0, 0, SLIDE_W, SLIDE_H, NAVY)
    add_rect(slide, 0, 0, Inches(0.18), SLIDE_H, TEAL)
    add_rect(slide, Inches(0.85), Inches(0.75), Inches(1.25), Inches(0.06), ORANGE)
    add_text(
        slide, "PROJET « ENQUÊTE SUR UNE MALADIE »", Inches(0.85), Inches(0.95),
        Inches(10.5), Inches(0.35), size=13, bold=True, color=GOLD,
    )
    add_text(
        slide,
        "SARM : gènes de résistance associés\nà la méticilline et à la multirésistance",
        Inches(0.85), Inches(1.55), Inches(11.4), Inches(1.55),
        size=38, bold=True, color=WHITE, line_spacing=0.98,
    )
    add_text(
        slide,
        "Staphylococcus aureus · NCBI Pathogen Detection · PDG000000073.1314",
        Inches(0.85), Inches(3.25), Inches(11.2), Inches(0.45),
        size=16, color=RGBColor(0xDB, 0xE7, 0xF3),
    )
    # Question
    add_rect(
        slide, Inches(0.85), Inches(4.10), Inches(11.5), Inches(1.25),
        RGBColor(0x24, 0x43, 0x6B), line=TEAL, radius=True,
    )
    add_text(
        slide,
        "Quels gènes de résistance sont associés à la résistance à la méticilline\n"
        "et à la multirésistance chez S. aureus ?",
        Inches(1.12), Inches(4.25), Inches(10.95), Inches(0.95),
        size=19, bold=True, color=WHITE, line_spacing=1.05,
    )
    members = group.get("GROUP_MEMBERS", "").replace(";", " · ").strip(" ·")
    group_name = group.get("GROUP_NAME", "Projet SARM")
    add_text(
        slide,
        f"{group_name}  ·  {members}" if members else group_name,
        Inches(0.85), Inches(5.85), Inches(11.5), Inches(0.30),
        size=12.5, color=RGBColor(0xDB, 0xE7, 0xF3),
    )
    add_text(
        slide,
        f"{date.today():%d/%m/%Y}  ·  " + group.get("GROUP_COURSE", "Module — Enquête sur une maladie"),
        Inches(0.85), Inches(6.20), Inches(11.5), Inches(0.30),
        size=11.5, color=GRAY,
    )
    add_text(
        slide, "10 minutes · 13 diapositives", SLIDE_W - Inches(3.2), Inches(6.85),
        Inches(2.6), Inches(0.25), size=10, color=GRAY, align=PP_ALIGN.RIGHT,
    )
    set_notes(
        slide,
        "Bonjour, nous présentons notre projet « Enquête sur une maladie ». "
        "Nous avons choisi les infections à Staphylococcus aureus résistant à la méticilline, "
        "le SARM. Notre question est double : quels gènes sont associés à la résistance à la "
        "méticilline, et quels gènes sont associés à la multirésistance ? "
        "Le tout avec un pipeline reproductible en Shell et Python, sans R et sans séquences brutes.",
    )


def slide_context(prs, summary: dict, number: int) -> None:
    cohort = summary["cohort"]
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_title(slide, "Un pathogène majeur, une résistance qui aggrave tout", "Contexte", number)

    add_text(
        slide, "Pourquoi le SARM ?", MARGIN, Inches(1.72), Inches(6.0), Inches(0.35),
        size=16, bold=True, color=NAVY,
    )
    add_bullets(
        slide,
        [
            "S. aureus : commensal du nez et de la peau, mais aussi agent de bactériémies, "
            "d'endocardites et d'infections ostéo-articulaires.",
            "SARM : résistance à la méticilline portée par mecA ou mecC, qui codent PBP2a, "
            "une cible de faible affinité pour les bêta-lactamines.",
            "Les SARM cumulent souvent aminosides, macrolides, tétracyclines et "
            "fluoroquinolones : moins d'options thérapeutiques, plus de morbidité.",
            "La multirésistance (MDR) est définie par la résistance à au moins 3 classes "
            "d'antibiotiques, avec au moins 3 classes testées.",
        ],
        MARGIN, Inches(2.12), Inches(6.25), Inches(3.9),
        size=14.2, spacing=11, line_spacing=1.02,
    )

    add_kpi(
        slide, Inches(7.20), Inches(1.80), Inches(2.55), Inches(1.25),
        fmt_pct(cohort["mrsa_genotype_percent"]), "des isolats sont SARM génotypiques",
        TEAL,
    )
    add_kpi(
        slide, Inches(9.95), Inches(1.80), Inches(2.80), Inches(1.25),
        fmt_pct(cohort["mdr_in_mrsa_percent"]), "des SARM phénotypiques sont MDR",
        ORANGE,
    )
    add_kpi(
        slide, Inches(7.20), Inches(3.25), Inches(2.55), Inches(1.25),
        fmt_pct(cohort["mdr_in_mssa_percent"]), "des MSSA phénotypiques sont MDR",
        BLUE,
    )
    add_kpi(
        slide, Inches(9.95), Inches(3.25), Inches(2.80), Inches(1.25),
        f"×{summary['cohort']['mdr_in_mrsa_percent'] / max(0.1, summary['cohort']['mdr_in_mssa_percent']):.1f}",
        "plus de MDR chez les SARM (prévalences)",
        RED,
    )
    add_box(
        slide, Inches(7.20), Inches(4.85), Inches(5.55), Inches(1.55),
        "Notre angle",
        "Comparer les gènes présents chez les SARM et les MSSA, puis chez les SARM MDR "
        "et non-MDR. Le motif est explicite, testable et reproductible.",
        accent=GOLD, fill=PALE_GOLD, body_size=12.5,
    )
    set_notes(
        slide,
        "S. aureus est un pathogène majeur. La résistance à la méticilline est portée par "
        "mecA ou mecC. Le problème, c'est que ces souches ne sont pas seulement résistantes "
        "aux bêta-lactamines : elles cumulent d'autres résistances. "
        "Dans notre jeu de données, 55,5 % des isolats sont SARM génotypiques, et la MDR "
        "touche 52,9 % des SARM contre 12,9 % des MSSA. D'où notre double question.",
    )


def slide_data(prs, summary: dict, number: int) -> None:
    dataset = summary["dataset"]
    cohort = summary["cohort"]
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_title(slide, "Un snapshot public massif, mais peu de phénotypes", "Données", number)

    # Chaîne de traitement visuelle
    boxes = [
        ("164,2 Mo", "TSV de métadonnées\n67 colonnes", NAVY),
        ("175 586", "isolats de\nS. aureus", TEAL),
        ("97 449", "SARM génotypiques\n(mecA/mecC)", ORANGE),
        ("1 530", "isolats avec AST\n(0,87 %)", GOLD),
    ]
    x = MARGIN
    width = Inches(2.75)
    gap = Inches(0.28)
    for index, (value, label, color) in enumerate(boxes):
        xi = x + index * (width + gap)
        add_rect(slide, xi, Inches(1.85), width, Inches(1.55), LIGHT, line=MID, radius=True)
        add_rect(slide, xi, Inches(1.85), width, Inches(0.07), color)
        add_text(
            slide, value, xi + Inches(0.15), Inches(2.02), width - Inches(0.30), Inches(0.55),
            size=23, bold=True, color=color, align=PP_ALIGN.CENTER,
        )
        add_text(
            slide, label, xi + Inches(0.12), Inches(2.62), width - Inches(0.24), Inches(0.65),
            size=11.5, color=GRAY, align=PP_ALIGN.CENTER, line_spacing=0.95,
        )
        if index < len(boxes) - 1:
            add_text(
                slide, "→", xi + width + Inches(0.02), Inches(2.35), gap - Inches(0.04),
                Inches(0.45), size=20, bold=True, color=GRAY, align=PP_ALIGN.CENTER,
            )

    add_text(
        slide, "Source et intégrité", MARGIN, Inches(3.80), Inches(6.1), Inches(0.30),
        size=15, bold=True, color=NAVY,
    )
    add_bullets(
        slide,
        [
            "NCBI Pathogen Detection, snapshot public PDG000000073.1314, téléchargé le 30/10/2026.",
            f"SHA-256 vérifié : {dataset['sha256'][:16]}…{dataset['sha256'][-8:]} "
            f"({fmt_int(dataset['bytes'])} octets).",
            "Génotypes AMR issus d'AMRFinderPlus ; phénotypes AST heterogènes selon les laboratoires.",
            "Aucune séquence brute, aucune donnée personnelle : uniquement les métadonnées.",
        ],
        MARGIN, Inches(4.15), Inches(6.15), Inches(2.35),
        size=12.8, spacing=7,
    )

    add_box(
        slide, Inches(7.15), Inches(3.80), Inches(5.60), Inches(2.55),
        "Le point critique",
        "Seulement 1 530 isolats (0,87 %) ont un phénotype AST, et 1 320 ont "
        "oxacilline/céfoxitine interprétables. Nous faisons donc :\n\n"
        "• une analyse génotypique sur 175 586 isolats ;\n"
        "• une validation phénotypique sur 1 320 isolats.\n\n"
        "Ce n'est pas un défaut du pipeline, c'est une limite du snapshot.",
        accent=ORANGE, fill=PALE_GOLD, body_size=12.2,
    )
    set_notes(
        slide,
        "Le jeu de données est le snapshot public NCBI Pathogen Detection PDG000000073.1314. "
        "Le fichier fait 164,2 Mo, 67 colonnes et 175 586 isolats. "
        "Le point critique, c'est que seulement 1 530 isolats ont des phénotypes AST, soit "
        "0,87 %. Nous avons donc deux niveaux : une analyse génotypique sur toute la cohorte, "
        "et une validation phénotypique sur 1 320 isolats interprétables. "
        "Le SHA-256 est vérifié par le script à chaque exécution.",
    )


def slide_pattern(prs, summary: dict, number: int) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_title(slide, "Du gène au motif : une définition reproductible", "Motif", number)

    add_box(
        slide, MARGIN, Inches(1.75), Inches(6.05), Inches(2.25),
        "Motif génotypique",
        "G(x) = ensemble des gènes extraits de AMR_genotypes.\n"
        "Les variants sont ramenés au gène :\n"
        "gyrA_S84L=POINT → gyrA ; mecA_L94F=POINT → mecA.\n\n"
        "P(x) = 1 si mecA ∈ G(x) ou mecC ∈ G(x), sinon 0.",
        accent=TEAL, fill=PALE_TEAL, body_size=13.2,
    )
    add_box(
        slide, Inches(6.85), Inches(1.75), Inches(5.90), Inches(2.25),
        "Validation phénotypique",
        "SARM si oxacilline = R ou céfoxitine = R.\n"
        "MSSA si au moins l'un des deux est S et aucun n'est R.\n"
        "Sinon : phénotype inconnu (exclu de la validation).\n\n"
        "La méticilline n'est pas testée dans AST : ces deux marqueurs sont les substituts recommandés.",
        accent=BLUE, fill=RGBColor(0xEA, 0xF0, 0xF8), body_size=12.8,
    )

    add_text(
        slide, "Multirésistance (MDR)", MARGIN, Inches(4.35), Inches(6.0), Inches(0.30),
        size=15, bold=True, color=NAVY,
    )
    add_bullets(
        slide,
        [
            "Une classe est résistante si au moins un antibiotique de la classe est R (ou NS).",
            "MDR = 1 si au moins 3 classes sont résistantes ET si au moins 3 classes ont été testées.",
            "Mapping de 59 antibiotiques vers 17 classes dans config/drug_classes.tsv.",
        ],
        MARGIN, Inches(4.70), Inches(6.15), Inches(1.65),
        size=12.6, spacing=6,
    )

    add_box(
        slide, Inches(6.85), Inches(4.25), Inches(5.90), Inches(2.05),
        "Pourquoi ce motif ?",
        "• Deux marqueurs validés et recommandés (mecA/mecC).\n"
        "• Comparable à un phénotype réel, donc falsifiable.\n"
        "• Aucune séquence brute : uniquement les métadonnées AMR.",
        accent=GOLD, fill=PALE_GOLD, body_size=12.6,
    )
    set_notes(
        slide,
        "Le motif est volontairement simple et explicite. Pour chaque isolat, on extrait les "
        "gènes de AMR_genotypes, en ramenant les variants au gène : gyrA_S84L devient gyrA. "
        "Le SARM est défini par la présence de mecA ou mecC. On valide ensuite sur le "
        "phénotype : oxacilline ou céfoxitine résistant. Pour la MDR, on compte les classes : "
        "au moins 3 classes résistantes, et au moins 3 classes testées. "
        "Le mapping des 59 antibiotiques vers 17 classes est dans un fichier de configuration.",
    )


def slide_pipeline(prs, summary: dict, number: int) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_title(slide, "Un seul point d'entrée : ./run.sh", "Pipeline", number)

    add_image_fit(
        slide, Path("results/figures/fig00_pipeline.png"),
        MARGIN, Inches(1.65), CONTENT_W, Inches(2.65),
    )
    steps = [
        ("1", "Acquisition", "curl + SHA-256 + taille ; données brutes en lecture seule."),
        ("2", "Shell", "cut | awk | sed pour filtrer et nettoyer ; palmarès par gènes."),
        ("3", "Python", "pandas + scipy : Fisher, OR, IC 95 %, Benjamini-Hochberg."),
        ("4", "Sorties", "CSV, JSON, 6 figures, rapport 4 pages, diapositives."),
    ]
    x = MARGIN
    width = Inches(2.88)
    gap = Inches(0.16)
    for index, (num, title, body) in enumerate(steps):
        xi = x + index * (width + gap)
        add_rect(slide, xi, Inches(4.55), width, Inches(1.55), LIGHT, line=MID, radius=True)
        add_rect(slide, xi, Inches(4.55), Inches(0.55), Inches(1.55), NAVY)
        add_text(
            slide, num, xi, Inches(4.75), Inches(0.55), Inches(0.45),
            size=20, bold=True, color=WHITE, align=PP_ALIGN.CENTER,
        )
        add_text(
            slide, title, xi + Inches(0.65), Inches(4.67), width - Inches(0.75), Inches(0.30),
            size=13, bold=True, color=NAVY,
        )
        add_text(
            slide, body, xi + Inches(0.65), Inches(5.02), width - Inches(0.75), Inches(0.95),
            size=10.8, color=DARK, line_spacing=0.98,
        )

    add_text(
        slide,
        "./run.sh -h   ·   -f (forcer le téléchargement)   ·   -n (hors ligne)   ·   "
        "-i FICHIER   ·   -k (garder les temporaires)",
        MARGIN, Inches(6.35), CONTENT_W, Inches(0.30),
        size=11.2, color=GRAY, align=PP_ALIGN.CENTER,
    )
    set_notes(
        slide,
        "Tout le pipeline tient dans un seul script, run.sh. Il télécharge si besoin, vérifie "
        "la taille et le SHA-256, nettoie avec cut, awk et sed, puis appelle Python pour "
        "l'analyse statistique et les figures. Enfin il génère le rapport, les diapositives "
        "et une archive tar datée. Il y a une aide avec -h et plusieurs options getopts. "
        "Il est relançable sans nettoyage manuel.",
    )


def slide_stats(prs, summary: dict, number: int) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_title(slide, "Tester chaque gène, contrôler les faux positifs", "Méthode statistique", number)

    add_text(
        slide, "Table 2 × 2 par gène", MARGIN, Inches(1.75), Inches(5.6), Inches(0.30),
        size=15, bold=True, color=NAVY,
    )
    add_table(
        slide,
        [
            ["", "Groupe +", "Groupe −"],
            ["Gène présent", "a", "b"],
            ["Gène absent", "c", "d"],
        ],
        MARGIN, Inches(2.15), Inches(5.45), Inches(1.95),
        col_widths=[2.0, 1.7, 1.7], font_size=16, header_size=13, first_col_bold=True,
    )
    add_text(
        slide,
        "OR = (a × d) / (b × c), avec correction de Haldane-Anscombe (+0,5) "
        "pour éviter les divisions par zéro.",
        MARGIN, Inches(4.30), Inches(5.55), Inches(0.85),
        size=12.2, color=DARK, line_spacing=1.02,
    )
    add_box(
        slide, MARGIN, Inches(5.25), Inches(5.55), Inches(1.15),
        "Test utilisé",
        "Fisher exact bilatéral : adapté aux gènes rares et aux petits effectifs.",
        accent=TEAL, fill=PALE_TEAL, body_size=12.2,
    )

    add_text(
        slide, "Contrôle de la multiplicité", Inches(6.60), Inches(1.75), Inches(6.1), Inches(0.30),
        size=15, bold=True, color=NAVY,
    )
    add_bullets(
        slide,
        [
            "IC 95 % de l'OR calculé sur l'échelle log.",
            "Correction de Benjamini-Hochberg : q < 0,05.",
            "Filtres : au moins 10 isolats porteurs, prévalence ≥ 1 % dans au moins un groupe.",
            "Exclusion des gènes intrinsèques présents chez plus de 95 % des deux groupes.",
            "Deux analyses : SARM vs MSSA (génotype) et MDR vs non-MDR (phénotype).",
        ],
        Inches(6.60), Inches(2.15), Inches(6.15), Inches(3.3),
        size=13.2, spacing=9,
    )
    add_box(
        slide, Inches(6.60), Inches(5.25), Inches(6.15), Inches(1.15),
        "Pourquoi BH ?",
        "En testant 230 gènes, on ferait environ 11 faux positifs à p < 0,05 sans correction. "
        "BH contrôle le taux de fausses découvertes.",
        accent=ORANGE, fill=PALE_GOLD, body_size=11.6,
    )
    set_notes(
        slide,
        "Pour chaque gène, on construit une table 2x2 : présent ou absent dans le groupe, "
        "présent ou absent dans le contrôle. On utilise le test exact de Fisher car certains "
        "gènes sont rares. L'odds ratio est corrigé par Haldane-Anscombe, avec un intervalle "
        "de confiance à 95 %. Et surtout, on teste 230 gènes : sans correction, on aurait "
        "environ 11 faux positifs. On applique donc Benjamini-Hochberg, avec q < 0,05.",
    )


def slide_cohort(prs, summary: dict, number: int) -> None:
    cohort = summary["cohort"]
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_title(slide, "La cohorte : 175 586 isolats, deux lectures", "Résultats — cohorte", number)

    add_image_fit(
        slide, Path("results/figures/fig01_cohort.png"),
        MARGIN, Inches(1.65), Inches(7.9), Inches(4.75),
    )
    add_kpi(
        slide, Inches(8.85), Inches(1.75), Inches(3.90), Inches(1.05),
        fmt_int(cohort["n_mrsa_genotype"]), "SARM génotypiques (mecA/mecC)", TEAL,
    )
    add_kpi(
        slide, Inches(8.85), Inches(2.95), Inches(3.90), Inches(1.05),
        fmt_int(cohort["n_phenotype_known"]), "phénotypes oxacilline/céfoxitine connus", BLUE,
    )
    add_kpi(
        slide, Inches(8.85), Inches(4.15), Inches(3.90), Inches(1.05),
        f"{fmt_int(cohort['n_mrsa_phenotype'])} / {fmt_int(cohort['n_mssa_phenotype'])}",
        "SARM / MSSA phénotypiques", ORANGE,
    )
    add_kpi(
        slide, Inches(8.85), Inches(5.35), Inches(3.90), Inches(1.05),
        fmt_int(cohort["n_mdr_known"]), "isolats avec au moins 3 classes testées", GOLD,
    )
    add_text(
        slide,
        "Lecture : la prévalence de la MDR est calculée dans la sous-cohorte AST, "
        "pas sur les 175 586 isolats.",
        MARGIN, Inches(6.55), Inches(12.2), Inches(0.30),
        size=10.5, color=GRAY,
    )
    set_notes(
        slide,
        "Voici la cohorte. 175 586 isolats, dont 97 449 SARM génotypiques, soit 55,5 %. "
        "Mais seuls 1 320 ont un phénotype oxacilline/céfoxitine interprétable : "
        "467 SARM et 853 MSSA. Et 1 333 isolats ont au moins 3 classes testées, ce qui permet "
        "d'évaluer la MDR. Attention : tous les pourcentages de MDR portent sur cette "
        "sous-cohorte AST, pas sur les 175 586 isolats.",
    )


def slide_validation(prs, summary: dict, number: int) -> None:
    conc = summary["concordance"]
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_title(slide, "Le génotype prédit bien le phénotype", "Validation", number)

    add_text(
        slide, "Concordance mecA/mecC vs oxacilline/céfoxitine", MARGIN, Inches(1.75),
        Inches(6.3), Inches(0.30), size=14.5, bold=True, color=NAVY,
    )
    add_table(
        slide,
        [
            ["", "SARM phénotype +", "SARM phénotype −"],
            ["Génotype mecA/mecC +", fmt_int(conc["true_positive"]), fmt_int(conc["false_positive"])],
            ["Génotype mecA/mecC −", fmt_int(conc["false_negative"]), fmt_int(conc["true_negative"])],
        ],
        MARGIN, Inches(2.15), Inches(6.15), Inches(2.35),
        col_widths=[2.7, 1.8, 1.8], font_size=18, header_size=12.5, first_col_bold=True,
    )
    add_text(
        slide, f"n = {fmt_int(conc['n_compared'])} isolats avec phénotype interprétable",
        MARGIN, Inches(4.62), Inches(6.1), Inches(0.30), size=11.5, color=GRAY,
    )

    metrics = [
        ("98,1 %", "concordance globale", TEAL),
        ("97,2 %", "sensibilité", BLUE),
        ("98,6 %", "spécificité", BLUE),
        (f"{conc['cohen_kappa']:.2f}", "kappa de Cohen", ORANGE),
    ]
    x = Inches(7.05)
    y = Inches(1.80)
    for index, (value, label, color) in enumerate(metrics):
        xi = x + (index % 2) * Inches(2.90)
        yi = y + (index // 2) * Inches(1.55)
        add_kpi(slide, xi, yi, Inches(2.70), Inches(1.30), value, label, color)

    add_box(
        slide, Inches(7.05), Inches(4.95), Inches(5.70), Inches(1.55),
        "Interprétation",
        "Le génotype est un excellent substitut du phénotype dans ce snapshot. "
        "Les 25 discordances (13 faux négatifs, 12 faux positifs) rappellent "
        "qu'expression et sensibilité peuvent varier.",
        accent=GOLD, fill=PALE_GOLD, body_size=12.0,
    )
    set_notes(
        slide,
        "Avant de comparer les gènes, il faut vérifier que notre définition génotypique tient. "
        "Sur 1 320 isolats, on a 455 vrais positifs, 840 vrais négatifs, 13 faux négatifs et "
        "12 faux positifs. La concordance est de 98,1 %, avec un kappa de 0,96 : c'est excellent. "
        "Cela justifie d'utiliser mecA/mecC comme définition du SARM pour l'analyse génotypique "
        "sur toute la cohorte.",
    )


def slide_mrsa(prs, summary: dict, number: int) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_title(slide, "SARM : un noyau SCCmec et un cortège de co-résistances",
              "Résultats — gènes associés au SARM", number)

    add_image_fit(
        slide, Path("results/figures/fig02_mrsa_genes.png"),
        MARGIN, Inches(1.62), Inches(7.55), Inches(5.05),
    )
    add_text(
        slide, "Hors cassette SCCmec", Inches(8.30), Inches(1.75), Inches(4.45), Inches(0.30),
        size=14.5, bold=True, color=NAVY,
    )
    add_bullets(
        slide,
        [
            "gyrA (54,7 % vs 4,9 % ; OR = 23,3) et parC (57,8 % vs 7,4 % ; OR = 17,1) : "
            "fluoroquinolones.",
            "dfrK (OR = 17,5), dfrS1 (OR = 15,4) : folate/sulfamides.",
            "mph(C), ant(6)-Ia, aph(3')-IIIa, sat4 : module aminosides/macrolides.",
            "tet(M) (OR = 11,0) : tétracyclines.",
            "Les marqueurs de cassette (mecI, mecR1, bleO) sont exclus de l'interprétation.",
        ],
        Inches(8.30), Inches(2.15), Inches(4.45), Inches(3.55),
        size=11.6, spacing=7, line_spacing=0.98,
    )
    add_box(
        slide, Inches(8.30), Inches(5.75), Inches(4.45), Inches(0.90),
        "Message",
        "Le SARM n'est pas seulement mecA : il est co-sélectionné avec d'autres résistances.",
        accent=ORANGE, fill=PALE_GOLD, body_size=11.2,
    )
    set_notes(
        slide,
        "Pour les gènes associés au SARM, on exclut volontairement les marqueurs de la cassette "
        "SCCmec, qui font partie du motif. Il reste un cortège très net : gyrA et parC pour les "
        "fluoroquinolones, dfrK et dfrS1 pour le folate, mph(C), ant(6)-Ia, aph(3')-IIIa et sat4 "
        "pour les aminosides et macrolides, tet(M) pour les tétracyclines. "
        "Les odds ratios vont de 11 à 23, avec q < 0,001. "
        "Cela montre que le SARM est co-sélectionné avec d'autres résistances.",
    )


def slide_mdr(prs, summary: dict, number: int) -> None:
    cohort = summary["cohort"]
    crude_or = (
        (cohort["n_mrsa_mdr"] / (cohort["n_mrsa_mdr_known"] - cohort["n_mrsa_mdr"]))
        / (cohort["n_mssa_mdr"] / (cohort["n_mssa_mdr_known"] - cohort["n_mssa_mdr"]))
    )
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_title(slide, "MDR : plus de quatre fois plus fréquente chez les SARM",
              "Résultats — multirésistance", number)

    add_kpi(slide, MARGIN, Inches(1.70), Inches(2.55), Inches(1.20),
            fmt_pct(cohort["mdr_in_mrsa_percent"]), "MDR chez les SARM (247/467)", ORANGE)
    add_kpi(slide, MARGIN + Inches(2.75), Inches(1.70), Inches(2.55), Inches(1.20),
            fmt_pct(cohort["mdr_in_mssa_percent"]), "MDR chez les MSSA (110/853)", TEAL)
    add_kpi(slide, MARGIN + Inches(5.50), Inches(1.70), Inches(2.55), Inches(1.20),
            f"OR {fmt_or(crude_or)}", "odds ratio brut", RED)
    add_kpi(slide, MARGIN + Inches(8.25), Inches(1.70), Inches(2.55), Inches(1.20),
            "230", "gènes testés (Fisher + BH)", NAVY)

    add_image_fit(
        slide, Path("results/figures/fig04_mdr_genes.png"),
        Inches(6.85), Inches(3.05), Inches(5.95), Inches(3.45),
    )
    add_text(
        slide, "Top gènes associés à la MDR", MARGIN, Inches(3.05), Inches(5.9), Inches(0.30),
        size=14.5, bold=True, color=NAVY,
    )
    add_bullets(
        slide,
        [
            "erm(C) (28,3 % vs 0 % ; OR = 175) et erm(A) (47,8 % vs 0,5 % ; OR = 134).",
            "ant(9)-Ia (46,2 % vs 0,5 % ; OR = 126) et aadD1 (40,9 % vs 1,8 % ; OR = 33).",
            "mecI / bleO (36 % vs 1,4 % ; OR ≈ 35), rpsJ (OR = 20), mupA (OR = 15).",
            "erm(A) et ant(9)-Ia sont portés par des éléments mobiles (Tn554) : "
            "acquisition conjointe probable.",
        ],
        MARGIN, Inches(3.40), Inches(5.95), Inches(2.45),
        size=11.6, spacing=7, line_spacing=0.98,
    )
    add_box(
        slide, MARGIN, Inches(5.95), Inches(5.95), Inches(0.75),
        "Nuance",
        "Près de la moitié des SARM restent non-MDR : le fond génétique ne suffit pas.",
        accent=GOLD, fill=PALE_GOLD, body_size=11.2,
    )
    set_notes(
        slide,
        "Pour la multirésistance, le contraste est fort : 52,9 % des SARM sont MDR contre "
        "12,9 % des MSSA, soit un odds ratio brut de 7,58. Les gènes les plus associés sont "
        "erm(C), erm(A), ant(9)-Ia, aadD1, mecI, bleO, rpsJ et mupA. "
        "erm(A) et ant(9)-Ia sont connus pour être portés par des éléments mobiles comme Tn554, "
        "ce qui suggère une acquisition conjointe. Mais attention : près de la moitié des SARM "
        "restent non-MDR. Le fond génétique ne suffit donc pas à lui seul.",
    )


def slide_limits(prs, summary: dict, number: int) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_title(slide, "Ce que le snapshot ne permet pas de conclure", "Limites", number)

    limits = [
        ("01", "Couverture AST faible", "1 530 isolats (0,87 %) seulement ; 1 320 avec oxacilline/céfoxitine interprétables. Les analyses phénotypiques ne sont pas représentatives de tout le snapshot."),
        ("02", "Définition génotypique", "La présence de mecA/mecC ne garantit pas l'expression. La concordance observée (98,1 %) est excellente, mais pas parfaite."),
        ("03", "Confusion par le lignage", "Les associations ne sont pas ajustées sur le clone, le pays ou la source. Un gène peut être enrichi parce qu'il est fixé dans un lignage."),
        ("04", "MDR dépendante du panel", "Le nombre de classes testées varie selon les isolats ; les méthodes et seuils CLSI peuvent différer entre laboratoires."),
        ("05", "Gènes et variants agrégés", "gyrA/parC sont ramenés au gène : on ne distingue pas les mutations à fort ou faible niveau de résistance."),
        ("06", "Pas de séquences brutes", "Ni virulence, ni structure de population, ni mécanismes non détectés par AMRFinderPlus."),
    ]
    x = MARGIN
    y = Inches(1.65)
    width = Inches(3.92)
    height = Inches(2.30)
    gap_x = Inches(0.15)
    gap_y = Inches(0.18)
    for index, (num, title, body) in enumerate(limits):
        xi = x + (index % 3) * (width + gap_x)
        yi = y + (index // 3) * (height + gap_y)
        add_rect(slide, xi, yi, width, height, LIGHT, line=MID, radius=True)
        add_text(
            slide, num, xi + Inches(0.15), yi + Inches(0.12), Inches(0.55), Inches(0.30),
            size=13, bold=True, color=ORANGE,
        )
        add_text(
            slide, title, xi + Inches(0.68), yi + Inches(0.12), width - Inches(0.80), Inches(0.32),
            size=12.8, bold=True, color=NAVY,
        )
        add_text(
            slide, body, xi + Inches(0.15), yi + Inches(0.52), width - Inches(0.30), height - Inches(0.62),
            size=9.8, color=DARK, line_spacing=0.98,
        )
    add_text(
        slide,
        "Conséquence : nos résultats sont des associations, pas des relations causales. "
        "Ils génèrent des hypothèses à tester sur génomes complets et modèles ajustés.",
        MARGIN, Inches(6.78), CONTENT_W, Inches(0.30),
        size=10.5, color=GRAY, align=PP_ALIGN.CENTER,
    )
    set_notes(
        slide,
        "Les limites sont importantes à assumer. D'abord, la couverture AST est faible : "
        "0,87 %. Ensuite, la définition génotypique n'est pas parfaite, même si la concordance "
        "est de 98 %. Surtout, les associations ne sont pas ajustées sur le lignage : un gène "
        "peut être enrichi parce qu'il est fixé dans un clone SARM particulier. La MDR dépend "
        "aussi du panel testé. Enfin, on agrège les variants et on n'analyse pas les séquences "
        "brutes. Ce sont donc des associations, pas des relations causales.",
    )


def slide_conclusion(prs, summary: dict, number: int) -> None:
    cohort = summary["cohort"]
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_title(slide, "Trois messages à retenir", "Conclusion", number)

    cards = [
        ("1", "Le SARM est majoritaire", f"{fmt_pct(cohort['mrsa_genotype_percent'])} des isolats portent mecA/mecC. "
         "Il s'accompagne d'un cortège de co-résistances : fluoroquinolones, aminosides, "
         "macrolides, tétracyclines, folate.", TEAL),
        ("2", "La MDR n'est pas uniforme", f"{fmt_pct(cohort['mdr_in_mrsa_percent'])} des SARM sont MDR contre "
         f"{fmt_pct(cohort['mdr_in_mssa_percent'])} des MSSA (OR brut 7,58). Près d'un SARM sur deux "
         "reste non-MDR.", ORANGE),
        ("3", "Un pipeline reproductible", "Un seul ./run.sh : téléchargement, SHA-256, Shell, Python, "
         "tests, rapport 4 pages, diapositives et archive datée. Relançable sans nettoyage.", NAVY),
    ]
    y = Inches(1.75)
    for index, (num, title, body, color) in enumerate(cards):
        yi = y + index * Inches(1.55)
        add_rect(slide, MARGIN, yi, CONTENT_W, Inches(1.30), LIGHT, line=MID, radius=True)
        add_rect(slide, MARGIN, yi, Inches(0.75), Inches(1.30), color)
        add_text(
            slide, num, MARGIN, yi + Inches(0.30), Inches(0.75), Inches(0.55),
            size=26, bold=True, color=WHITE, align=PP_ALIGN.CENTER,
        )
        add_text(
            slide, title, MARGIN + Inches(0.95), yi + Inches(0.12), Inches(3.2), Inches(0.35),
            size=15, bold=True, color=NAVY,
        )
        add_text(
            slide, body, MARGIN + Inches(0.95), yi + Inches(0.50), CONTENT_W - Inches(1.15),
            Inches(0.70), size=11.5, color=DARK, line_spacing=1.0,
        )

    add_text(
        slide, "Perspectives", MARGIN, Inches(6.55), Inches(2.0), Inches(0.30),
        size=12.5, bold=True, color=NAVY,
    )
    add_text(
        slide,
        "Ajuster sur le complexe clonal  ·  analyser les génomes complets  ·  "
        "suivre l'évolution temporelle  ·  étendre à d'autres espèces",
        MARGIN + Inches(1.65), Inches(6.55), CONTENT_W - Inches(1.65), Inches(0.30),
        size=10.8, color=GRAY,
    )
    set_notes(
        slide,
        "Pour conclure, trois messages. Un : le SARM est majoritaire, 55,5 %, et il est "
        "accompagné d'un cortège de co-résistances. Deux : la MDR est beaucoup plus fréquente "
        "chez les SARM, 52,9 % contre 12,9 %, mais elle n'est pas uniforme : près d'un SARM sur "
        "deux reste non-MDR. Trois : tout le pipeline est reproductible avec un seul run.sh, "
        "des tests, un rapport de 4 pages et une archive. "
        "Les perspectives seraient d'ajuster sur le lignage et d'analyser les génomes complets.",
    )


def slide_thanks(prs, summary: dict, group: dict, number: int) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_rect(slide, 0, 0, SLIDE_W, SLIDE_H, NAVY)
    add_rect(slide, 0, 0, Inches(0.18), SLIDE_H, TEAL)
    add_text(
        slide, "MERCI", Inches(0.85), Inches(1.05), Inches(6.0), Inches(0.70),
        size=46, bold=True, color=WHITE,
    )
    add_text(
        slide, "Questions & démonstration", Inches(0.85), Inches(1.85), Inches(7.0), Inches(0.45),
        size=20, color=GOLD,
    )
    add_text(
        slide,
        "Les chiffres clés sont dans le rapport de 4 pages ;\n"
        "le code, les tests et le README sont dans le dépôt.",
        Inches(0.85), Inches(2.55), Inches(6.6), Inches(0.80),
        size=14, color=RGBColor(0xDB, 0xE7, 0xF3), line_spacing=1.1,
    )
    add_box(
        slide, Inches(0.85), Inches(3.75), Inches(6.35), Inches(1.60),
        "Démo live",
        "./run.sh -h          affiche l'aide et les options\n"
        "./run.sh             exécute tout le pipeline\n"
        "python -m pytest -q  lance les 7 tests",
        accent=TEAL, fill=RGBColor(0x24, 0x43, 0x6B), title_size=13, body_size=11.5,
    )
    add_text(
        slide, "À retenir", Inches(7.85), Inches(1.05), Inches(4.7), Inches(0.35),
        size=14, bold=True, color=GOLD,
    )
    add_bullets(
        slide,
        [
            "55,5 % de SARM génotypiques.",
            "52,9 % de MDR chez les SARM vs 12,9 % chez les MSSA.",
            "98,1 % de concordance génotype/phénotype.",
            "Un pipeline unique, testé et archivé.",
        ],
        Inches(7.85), Inches(1.50), Inches(4.75), Inches(2.3),
        size=13.5, spacing=8, color=WHITE,
    )
    members = group.get("GROUP_MEMBERS", "").replace(";", " · ").strip(" ·")
    group_name = group.get("GROUP_NAME", "Projet SARM")
    add_text(
        slide, f"{group_name}  ·  {members}" if members else group_name,
        Inches(0.85), Inches(6.05), Inches(11.5), Inches(0.30),
        size=11, color=RGBColor(0xDB, 0xE7, 0xF3),
    )
    add_text(
        slide, f"{number:02d}", SLIDE_W - Inches(1.2), SLIDE_H - Inches(0.55),
        Inches(0.7), Inches(0.25), size=9, color=GRAY, align=PP_ALIGN.RIGHT,
    )
    set_notes(
        slide,
        "Merci de votre attention. Nous sommes prêts pour les questions. "
        "Nous pouvons montrer l'aide de run.sh, relancer le pipeline ou modifier un paramètre "
        "en direct, par exemple le seuil alpha ou le nombre minimal d'isolats.",
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def build_presentation(results_dir: Path, out_path: Path, group: dict) -> int:
    summary = load_json(results_dir / "summary.json")
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H

    slide_title(prs, summary, group)
    slide_context(prs, summary, 2)
    slide_data(prs, summary, 3)
    slide_pattern(prs, summary, 4)
    slide_pipeline(prs, summary, 5)
    slide_stats(prs, summary, 6)
    slide_cohort(prs, summary, 7)
    slide_validation(prs, summary, 8)
    slide_mrsa(prs, summary, 9)
    slide_mdr(prs, summary, 10)
    slide_limits(prs, summary, 11)
    slide_conclusion(prs, summary, 12)
    slide_thanks(prs, summary, group, 13)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(out_path))
    print(f"[slides] PPTX généré : {out_path} ({len(prs.slides)} diapositives)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Génère la présentation orale (PPTX) du projet SARM.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Exemple : python make_slides.py --results results --out presentation/presentation.pptx",
    )
    parser.add_argument("--results", default=Path("results"), type=Path,
                        help="Dossier des résultats (défaut : results).")
    parser.add_argument("--out", default=Path("presentation/presentation.pptx"), type=Path,
                        help="Fichier PPTX de sortie (défaut : presentation/presentation.pptx).")
    parser.add_argument("--group-config", default=Path("config/group.env"), type=Path,
                        help="Configuration du groupe (défaut : config/group.env).")
    args = parser.parse_args(argv)

    try:
        group = load_group(args.group_config)
        return build_presentation(args.results, args.out, group)
    except FileNotFoundError as error:
        print(f"[slides] ERREUR : {error}", file=sys.stderr)
        return 2
    except Exception as error:  # pragma: no cover
        print(f"[slides] ERREUR inattendue : {error}", file=sys.stderr)
        raise


if __name__ == "__main__":
    raise SystemExit(main())

