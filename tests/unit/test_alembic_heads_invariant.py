# -*- coding: utf-8 -*-
"""Unit-Test fuer K1: Alembic Single-Head-Invariant.

Vor dem Fix existierten 15 dangling Heads in alembic/versions/, sodass
`alembic upgrade head` mit "Multiple head revisions are present" fehlschlug.
Migration 262_merge_all_dangling_heads.py konsolidiert sie zu einem Head.

Dieser Test schuetzt die Invariante: kein Commit darf einen weiteren Head
einfuehren ohne ihn explizit zu mergen. Spiegelt den CI-Job
`alembic-heads-check` in .github/workflows/ci.yml.

Feinpoliert und durchdacht - Migration-Graph-Single-Head-Guard.
"""

import ast
import os
import pytest


pytestmark = [pytest.mark.unit]


def _enumerate_revisions(versions_dir: str):
    """AST-Parser fuer alembic-Revision-Files. Liefert {filename: (rev, down)}."""
    revisions = {}
    for f in sorted(os.listdir(versions_dir)):
        if not f.endswith(".py") or f.startswith("__"):
            continue
        with open(os.path.join(versions_dir, f), "rb") as fh:
            content = fh.read().decode("utf-8", errors="ignore")
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue

        rev = down = None
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = (
                    node.targets if isinstance(node, ast.Assign) else [node.target]
                )
                for tgt in targets:
                    if isinstance(tgt, ast.Name):
                        try:
                            value = ast.literal_eval(node.value)
                        except Exception:
                            continue
                        if tgt.id == "revision":
                            rev = value
                        elif tgt.id == "down_revision":
                            down = value
        if rev:
            revisions[f] = (rev, down)
    return revisions


def _compute_heads(revisions):
    all_revs = {v[0] for v in revisions.values()}
    referenced = set()
    for _, (_, down) in revisions.items():
        if down is None:
            continue
        if isinstance(down, str):
            referenced.add(down)
        elif isinstance(down, tuple):
            for r in down:
                if isinstance(r, str):
                    referenced.add(r)
    return sorted(all_revs - referenced)


class TestAlembicSingleHead:
    """K1: Migration-Graph hat genau einen Head."""

    def test_exactly_one_head(self):
        repo_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        versions = os.path.join(repo_root, "alembic", "versions")
        revisions = _enumerate_revisions(versions)
        heads = _compute_heads(revisions)
        assert len(heads) == 1, (
            f"Erwarte genau 1 alembic head, gefunden {len(heads)}: {heads}. "
            "Erzeuge eine Merge-Revision oder dokumentiere bewusste Branches."
        )

    def test_head_is_262(self):
        """Aktueller Head muss 262 (merge_all_dangling_heads) sein."""
        repo_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        versions = os.path.join(repo_root, "alembic", "versions")
        revisions = _enumerate_revisions(versions)
        heads = _compute_heads(revisions)
        assert heads == ["262"], f"Erwarte head '262', gefunden {heads}"

    def test_no_orphan_revisions(self):
        """Jede down_revision muss auf eine existierende Revision verweisen."""
        repo_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        versions = os.path.join(repo_root, "alembic", "versions")
        revisions = _enumerate_revisions(versions)
        all_revs = {v[0] for v in revisions.values()}
        orphans = []
        for fname, (rev, down) in revisions.items():
            if down is None:
                continue
            refs = [down] if isinstance(down, str) else list(down)
            for r in refs:
                if isinstance(r, str) and r not in all_revs:
                    orphans.append(f"{fname}: down_revision={r!r} nicht gefunden")
        assert not orphans, "Orphaned down_revisions:\n" + "\n".join(orphans)
