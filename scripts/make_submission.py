#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Construit l'archive de remise Projet_Maladie_Groupe_XX.zip.

Le script part de ``git archive HEAD`` (donc du commit final), ajoute une
copie de ``report/rapport.pdf`` à la racine de l'archive, exclut les données
brutes, l'environnement virtuel et les résultats régénérés, puis vérifie :

- la présence de ``run.sh``, ``scripts/``, ``README.md``, ``SOURCES.md``,
  ``LIEN_GIT.txt`` et ``rapport.pdf`` ;
- la présence du hash de commit dans ``LIEN_GIT.txt`` (substitution
  ``export-subst`` de ``git archive``) ;
- le bit exécutable de ``run.sh`` et des scripts Python ;
- l'absence de ``results/``, ``logs/``, ``tmp/``, ``data/raw/``,
  ``data/processed/`` et ``.venv/``.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "run.sh",
    "scripts/analysis.py",
    "scripts/report.py",
    "scripts/make_slides.py",
    "README.md",
    "SOURCES.md",
    "LIEN_GIT.txt",
    "requirements.txt",
    "rapport.pdf",
]
EXCLUDED = [
    "results",
    "logs",
    "tmp",
    "data/raw",
    "data/processed",
    ".venv",
    "__pycache__",
    ".pytest_cache",
]
EXECUTABLES = [
    "run.sh",
    "scripts/analysis.py",
    "scripts/report.py",
    "scripts/make_slides.py",
    "scripts/tests/test_analysis.py",
]


def read_group_name() -> str:
    """Lit GROUP_NAME dans config/group.env, avec une valeur de repli."""
    cfg = ROOT / "config/group.env"
    if cfg.is_file():
        for line in cfg.read_text(encoding="utf-8").splitlines():
            if line.startswith("GROUP_NAME="):
                return line.split("=", 1)[1].strip().strip("\"'")
    return "Groupe SARM"


def group_suffix(name: str) -> str:
    """Transforme « Groupe 07 » ou « Groupe SARM » en suffixe de fichier."""
    match = re.search(r"\b(\d{1,3})\b", name)
    if match:
        return match.group(1)
    cleaned = re.sub(r"^Groupe\s*", "", name, flags=re.IGNORECASE)
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", cleaned).strip("_")
    return cleaned or "SARM"


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def build_archive(output: Path, keep_results: bool, allow_dirty: bool) -> int:
    status = git("status", "--porcelain")
    if status.returncode != 0:
        print("ERREUR : dépôt Git introuvable.", file=sys.stderr)
        return 1
    if status.stdout.strip() and not allow_dirty:
        print(
            "ERREUR : le dépôt contient des modifications non commitées.\n"
            "         Committer puis relancer, ou utiliser --allow-dirty.",
            file=sys.stderr,
        )
        return 1

    with tempfile.TemporaryDirectory(prefix="sarm_submission_") as tmp:
        base = Path(tmp) / "base.zip"
        result = git(
            "archive",
            "--format=zip",
            f"--output={base}",
            "HEAD",
        )
        if result.returncode != 0:
            print(result.stderr, file=sys.stderr)
            return 1

        if output.exists():
            output.unlink()
        output.parent.mkdir(parents=True, exist_ok=True)

        excluded = [p for p in EXCLUDED if not (keep_results and p == "results")]
        with zipfile.ZipFile(base) as source, zipfile.ZipFile(
            output, "w", zipfile.ZIP_DEFLATED
        ) as target:
            for info in source.infolist():
                name = info.filename
                if name.endswith("/"):
                    continue
                if any(name == p or name.startswith(p + "/") for p in excluded):
                    continue
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                if (info.external_attr >> 16) & 0o111:
                    info.external_attr = 0o100755 << 16
                else:
                    info.external_attr = 0o100644 << 16
                target.writestr(info, source.read(name))

            pdf = ROOT / "report/rapport.pdf"
            if not pdf.is_file():
                print(
                    "ERREUR : report/rapport.pdf absent ; lancer ./run.sh -n.",
                    file=sys.stderr,
                )
                return 1
            info = zipfile.ZipInfo("rapport.pdf")
            info.date_time = time.localtime(pdf.stat().st_mtime)[:6]
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            target.writestr(info, pdf.read_bytes())

    return verify_archive(output)


def verify_archive(path: Path) -> int:
    errors: list[str] = []
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        for required in REQUIRED:
            if required not in names:
                errors.append(f"livrable absent : {required}")

        lien = archive.read("LIEN_GIT.txt").decode("utf-8", errors="replace")
        if "$Format" in lien or not re.search(r"\b[0-9a-f]{40}\b", lien):
            errors.append("LIEN_GIT.txt ne contient pas le hash du commit")
        if not re.search(
            r"https://github\.com/[^/\s]+/Projet_Maladie_SARM", lien
        ):
            errors.append("LIEN_GIT.txt ne contient pas l'URL du dépôt")

        for script in EXECUTABLES:
            if script in names:
                mode = archive.getinfo(script).external_attr >> 16
                if not mode & 0o111:
                    errors.append(f"bit exécutable absent : {script}")

        for prefix in ("results/", "logs/", "tmp/", "data/raw/", "data/processed/", ".venv/"):
            if any(name.startswith(prefix) for name in names):
                errors.append(f"contenu interdit dans l'archive : {prefix}")

    if errors:
        print("ÉCHEC de la vérification :", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    size = path.stat().st_size
    print(f"Archive  : {path}")
    print(f"Taille   : {size / 1024:.1f} Ko")
    print(f"Commit   : {git('rev-parse', 'HEAD').stdout.strip()}")
    print("Vérifié  : run.sh, scripts, README.md, SOURCES.md, LIEN_GIT.txt, rapport.pdf")
    print("Exclus   : results/, logs/, tmp/, data/raw/, data/processed/, .venv/")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Construit et vérifie l'archive de remise SARM.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemple :\n"
            "  python scripts/make_submission.py\n"
            "  python scripts/make_submission.py --output ../Projet_Maladie_Groupe_07.zip\n"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="archive de sortie (défaut : ../Projet_Maladie_Groupe_<groupe>.zip)",
    )
    parser.add_argument(
        "--group",
        default=None,
        help="suffixe du nom de groupe (défaut : lu dans config/group.env)",
    )
    parser.add_argument(
        "--keep-results",
        action="store_true",
        help="inclure results/ (déconseillé : le correcteur doit régénérer)",
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="autoriser une archive depuis un dépôt non commité",
    )
    args = parser.parse_args()

    suffix = args.group or group_suffix(read_group_name())
    output = args.output or (ROOT.parent / f"Projet_Maladie_Groupe_{suffix}.zip")
    output = output.resolve()

    return build_archive(output, args.keep_results, args.allow_dirty)


if __name__ == "__main__":
    sys.exit(main())
