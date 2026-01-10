"""
Lexware Kunden/Lieferanten Import Service.

Importiert Lexware-Exportdaten (Excel) aus beiden Firmen (Folie & Messer)
in das BusinessEntity-Modell.

Features:
- Automatisches Konflikt-Handling (kritische überspringen, harmlose mergen)
- Namensvarianten-Erkennung und Zusammenführung
- Duplikat-Erkennung innerhalb von Listen
"""

import json
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

import pandas as pd
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BusinessEntity, EntityType

logger = structlog.get_logger(__name__)


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class ImportResult:
    """Ergebnis eines Import-Vorgangs."""

    imported_count: int = 0
    skipped_count: int = 0
    merged_count: int = 0
    duplicate_count: int = 0
    error_count: int = 0
    skipped_entities: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class CustomerRecord:
    """Ein Kunden-Datensatz aus Lexware."""

    kd_nr: str
    matchcode: str
    firma: str
    name: str
    vorname: str
    plz: str
    ort: str
    strasse: str
    haus_nr: str
    email: str
    company: str  # 'folie' oder 'messer'

    # Optional (nur bei Messer)
    tel1: str = ""
    tel2: str = ""
    tel3: str = ""
    mobil: str = ""
    iban: str = ""
    bic: str = ""
    debitoren_nr: str = ""


@dataclass
class SupplierRecord:
    """Ein Lieferanten-Datensatz aus Lexware."""

    lief_nr: str
    matchcode: str
    firma: str
    name: str
    vorname: str
    plz: str
    ort: str
    konto_nr: str
    tel1: str
    tel2: str
    strasse: str
    haus_nr: str
    email: str
    iban: str
    kreditoren_nr: str
    bic: str
    company: str  # 'folie' oder 'messer'


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def normalize_text(text: str) -> str:
    """Normalisiert Text für Vergleiche."""
    if not text or pd.isna(text):
        return ""
    text = str(text).strip().lower()
    # Unicode normalisieren
    text = unicodedata.normalize("NFC", text)
    # Mehrfache Leerzeichen entfernen
    text = re.sub(r"\s+", " ", text)
    return text


def calculate_similarity(text1: str, text2: str) -> float:
    """Berechnet Ähnlichkeit zwischen zwei Texten (0.0-1.0)."""
    if not text1 or not text2:
        return 0.0
    return SequenceMatcher(None, normalize_text(text1), normalize_text(text2)).ratio()


def is_placeholder(text: str) -> bool:
    """Prüft ob Text ein Platzhalter ist (., -, leer)."""
    if not text or pd.isna(text):
        return True
    cleaned = str(text).strip()
    return cleaned in ("", ".", "-", "--", "---", "n/a", "n.a.", "keine")


def clean_customer_number(kd_nr: str) -> str:
    """Bereinigt Kundennummer."""
    if not kd_nr or pd.isna(kd_nr):
        return ""
    # Nur Ziffern und Buchstaben behalten
    return re.sub(r"[^\w]", "", str(kd_nr).strip())


# ============================================================================
# LEXWARE IMPORT SERVICE
# ============================================================================


class LexwareImportService:
    """Service für Lexware-Datenimport."""

    # Schwellenwerte
    CRITICAL_SIMILARITY_THRESHOLD = 0.5  # Unter diesem Wert = kritischer Konflikt
    HARMLESS_SIMILARITY_THRESHOLD = 0.7  # Über diesem Wert = harmlose Variante

    def __init__(self, db: AsyncSession) -> None:
        """Initialisiert den Service."""
        self.db = db
        self._conflict_analysis: dict[str, Any] = {}

    async def import_customers(
        self,
        folie_file: Path,
        messer_file: Path,
        skip_conflicts: bool = True,
        conflict_analysis_file: Optional[Path] = None,
    ) -> ImportResult:
        """
        Importiert Kunden aus beiden Firmen.

        Args:
            folie_file: Pfad zur Folie-Kundenliste (Excel)
            messer_file: Pfad zur Messer-Kundenliste (Excel)
            skip_conflicts: Kritische Konflikte überspringen
            conflict_analysis_file: Optional vorberechnete Konfliktanalyse

        Returns:
            ImportResult mit Statistiken
        """
        result = ImportResult()

        logger.info(
            "customer_import_started",
            folie_file=str(folie_file),
            messer_file=str(messer_file),
        )

        try:
            # 1. Excel-Dateien laden
            folie_df = self._load_customer_excel(folie_file, "folie")
            messer_df = self._load_customer_excel(messer_file, "messer")

            logger.info(
                "excel_files_loaded",
                folie_count=len(folie_df),
                messer_count=len(messer_df),
            )

            # 2. Konfliktanalyse laden oder berechnen
            if conflict_analysis_file and conflict_analysis_file.exists():
                with open(conflict_analysis_file, encoding="utf-8") as f:
                    self._conflict_analysis = json.load(f)
            else:
                self._conflict_analysis = self._analyze_customer_conflicts(
                    folie_df, messer_df
                )

            critical_kd_nrs = {
                c["Kd_Nr"] for c in self._conflict_analysis.get("kritische_konflikte", [])
            }

            # 3. Kunden zusammenführen
            all_kd_nrs = set(folie_df["Kd_Nr"].astype(str)) | set(
                messer_df["Kd_Nr"].astype(str)
            )

            for kd_nr in all_kd_nrs:
                kd_nr_clean = clean_customer_number(kd_nr)
                if not kd_nr_clean:
                    continue

                # Kritischen Konflikt überspringen?
                if skip_conflicts and kd_nr_clean in critical_kd_nrs:
                    result.skipped_count += 1
                    result.skipped_entities.append(
                        {"kd_nr": kd_nr_clean, "reason": "critical_conflict"}
                    )
                    continue

                # Daten aus beiden Firmen holen
                folie_row = folie_df[folie_df["Kd_Nr"].astype(str) == kd_nr]
                messer_row = messer_df[messer_df["Kd_Nr"].astype(str) == kd_nr]

                try:
                    entity = await self._create_customer_entity(
                        kd_nr_clean,
                        folie_row.iloc[0] if len(folie_row) > 0 else None,
                        messer_row.iloc[0] if len(messer_row) > 0 else None,
                    )
                    self.db.add(entity)
                    result.imported_count += 1
                except Exception as e:
                    result.error_count += 1
                    result.errors.append(f"Kunde {kd_nr_clean}: {str(e)}")
                    logger.error(
                        "customer_import_error", kd_nr=kd_nr_clean, error=str(e)
                    )

            await self.db.commit()

            logger.info(
                "customer_import_completed",
                imported=result.imported_count,
                skipped=result.skipped_count,
                errors=result.error_count,
            )

        except Exception as e:
            await self.db.rollback()
            result.errors.append(f"Import failed: {str(e)}")
            logger.exception("customer_import_failed", error=str(e))

        return result

    async def import_suppliers(
        self,
        folie_file: Path,
        messer_file: Path,
        skip_conflicts: bool = True,
        conflict_analysis_file: Optional[Path] = None,
    ) -> ImportResult:
        """
        Importiert Lieferanten aus beiden Firmen.

        Lieferanten werden nach Namen zusammengeführt (nicht nach Nummer),
        da die Nummern zwischen den Firmen nicht synchron waren.

        Args:
            folie_file: Pfad zur Folie-Lieferantenliste (Excel)
            messer_file: Pfad zur Messer-Lieferantenliste (Excel)
            skip_conflicts: Kritische Konflikte überspringen
            conflict_analysis_file: Optional vorberechnete Konfliktanalyse

        Returns:
            ImportResult mit Statistiken
        """
        result = ImportResult()

        logger.info(
            "supplier_import_started",
            folie_file=str(folie_file),
            messer_file=str(messer_file),
        )

        try:
            # 1. Excel-Dateien laden
            folie_df = self._load_supplier_excel(folie_file, "folie")
            messer_df = self._load_supplier_excel(messer_file, "messer")

            logger.info(
                "excel_files_loaded",
                folie_count=len(folie_df),
                messer_count=len(messer_df),
            )

            # 2. Konfliktanalyse laden oder berechnen
            if conflict_analysis_file and conflict_analysis_file.exists():
                with open(conflict_analysis_file, encoding="utf-8") as f:
                    self._conflict_analysis = json.load(f)
            else:
                self._conflict_analysis = self._analyze_supplier_conflicts(
                    folie_df, messer_df
                )

            # 3. Lieferanten nach normalisiertem Namen gruppieren
            name_groups: dict[str, list[pd.Series]] = {}

            for _, row in folie_df.iterrows():
                name_key = self._get_supplier_name_key(row)
                if name_key:
                    if name_key not in name_groups:
                        name_groups[name_key] = []
                    name_groups[name_key].append(row)

            for _, row in messer_df.iterrows():
                name_key = self._get_supplier_name_key(row)
                if name_key:
                    # Prüfe auf ähnliche existierende Namen
                    matched_key = self._find_similar_name_key(name_key, name_groups.keys())
                    if matched_key:
                        name_groups[matched_key].append(row)
                        result.merged_count += 1
                    else:
                        name_groups[name_key] = [row]

            # 4. Entities erstellen
            for name_key, rows in name_groups.items():
                try:
                    entity = await self._create_supplier_entity(name_key, rows)
                    self.db.add(entity)
                    result.imported_count += 1
                except Exception as e:
                    result.error_count += 1
                    result.errors.append(f"Lieferant {name_key}: {str(e)}")
                    logger.error(
                        "supplier_import_error", name=name_key, error=str(e)
                    )

            await self.db.commit()

            logger.info(
                "supplier_import_completed",
                imported=result.imported_count,
                merged=result.merged_count,
                skipped=result.skipped_count,
                errors=result.error_count,
            )

        except Exception as e:
            await self.db.rollback()
            result.errors.append(f"Import failed: {str(e)}")
            logger.exception("supplier_import_failed", error=str(e))

        return result

    # ========================================================================
    # PRIVATE METHODS - Excel Loading
    # ========================================================================

    def _load_customer_excel(self, file_path: Path, company: str) -> pd.DataFrame:
        """Lädt Kunden-Excel und normalisiert Spalten."""
        df = pd.read_excel(file_path)

        # Spalten normalisieren (verschiedene Formate zwischen Folie/Messer)
        column_map = {
            "I": "I",
            "Kd_Nr": "Kd_Nr",
            "Matchcode": "Matchcode",
            "Firma": "Firma",
            "Name": "Name",
            "Vorname": "Vorname",
            "PLZ": "PLZ",
            "Ort": "Ort",
            "Strasse": "Strasse",
            "HausNr": "HausNr",
            "Email": "Email",
        }

        # Company-Marker hinzufügen
        df["Company"] = company

        return df

    def _load_supplier_excel(self, file_path: Path, company: str) -> pd.DataFrame:
        """Lädt Lieferanten-Excel und normalisiert Spalten."""
        df = pd.read_excel(file_path)
        df["Company"] = company
        return df

    # ========================================================================
    # PRIVATE METHODS - Conflict Analysis
    # ========================================================================

    def _analyze_customer_conflicts(
        self, folie_df: pd.DataFrame, messer_df: pd.DataFrame
    ) -> dict[str, Any]:
        """Analysiert Konflikte zwischen Kunden-Listen."""
        conflicts = {"kritische_konflikte": [], "harmlose_varianten": []}

        folie_by_nr = {str(row["Kd_Nr"]): row for _, row in folie_df.iterrows()}
        messer_by_nr = {str(row["Kd_Nr"]): row for _, row in messer_df.iterrows()}

        common_nrs = set(folie_by_nr.keys()) & set(messer_by_nr.keys())

        for kd_nr in common_nrs:
            f_row = folie_by_nr[kd_nr]
            m_row = messer_by_nr[kd_nr]

            mc_sim = calculate_similarity(
                str(f_row.get("Matchcode", "")), str(m_row.get("Matchcode", ""))
            )

            if mc_sim < self.CRITICAL_SIMILARITY_THRESHOLD:
                conflicts["kritische_konflikte"].append({"Kd_Nr": kd_nr})
            elif mc_sim < 1.0:
                conflicts["harmlose_varianten"].append({"Kd_Nr": kd_nr})

        return conflicts

    def _analyze_supplier_conflicts(
        self, folie_df: pd.DataFrame, messer_df: pd.DataFrame
    ) -> dict[str, Any]:
        """Analysiert Konflikte zwischen Lieferanten-Listen."""
        # Lieferanten werden nach Namen gemapped, nicht nach Nummer
        return {"kritische_konflikte": [], "namensvarianten": []}

    # ========================================================================
    # PRIVATE METHODS - Entity Creation
    # ========================================================================

    async def _create_customer_entity(
        self,
        kd_nr: str,
        folie_row: Optional[pd.Series],
        messer_row: Optional[pd.Series],
    ) -> BusinessEntity:
        """Erstellt BusinessEntity aus Kundendaten."""
        # Beste Datenquelle wählen (nicht-leere Werte bevorzugen)
        def best_value(*values: Any) -> str:
            for v in values:
                if v and not is_placeholder(str(v)):
                    return str(v).strip()
            return ""

        # Matchcode bestimmen (für display_name)
        matchcode_folie = best_value(folie_row.get("Matchcode") if folie_row is not None else "")
        matchcode_messer = best_value(messer_row.get("Matchcode") if messer_row is not None else "")
        matchcode = matchcode_folie or matchcode_messer

        # Name für Anzeige: Kundennummer_Matchcode
        display_name = f"{kd_nr}_{matchcode}" if matchcode else kd_nr

        # Firma
        firma_folie = best_value(folie_row.get("Firma") if folie_row is not None else "")
        firma_messer = best_value(messer_row.get("Firma") if messer_row is not None else "")
        firma = firma_folie or firma_messer

        # Adresse
        strasse = best_value(
            folie_row.get("Strasse") if folie_row is not None else "",
            messer_row.get("Strasse") if messer_row is not None else "",
        )
        haus_nr = best_value(
            folie_row.get("HausNr") if folie_row is not None else "",
            messer_row.get("HausNr") if messer_row is not None else "",
        )
        plz = best_value(
            folie_row.get("PLZ") if folie_row is not None else "",
            messer_row.get("PLZ") if messer_row is not None else "",
        )
        ort = best_value(
            folie_row.get("Ort") if folie_row is not None else "",
            messer_row.get("Ort") if messer_row is not None else "",
        )
        email = best_value(
            folie_row.get("Email") if folie_row is not None else "",
            messer_row.get("Email") if messer_row is not None else "",
        )

        # IBAN (nur Messer hat diese Daten)
        iban = ""
        bic = ""
        if messer_row is not None:
            iban = best_value(messer_row.get("IBAN", ""))
            bic = best_value(messer_row.get("BIC", ""))

        # Company Presence
        companies = []
        if folie_row is not None:
            companies.append("folie")
        if messer_row is not None:
            companies.append("messer")

        # Lexware IDs
        lexware_ids: dict[str, dict[str, str]] = {}
        if folie_row is not None:
            lexware_ids["folie"] = {
                "kd_nr": kd_nr,
                "matchcode": matchcode_folie,
            }
        if messer_row is not None:
            lexware_ids["messer"] = {
                "kd_nr": kd_nr,
                "matchcode": matchcode_messer,
            }

        # Name Aliases (Varianten sammeln)
        aliases = set()
        if matchcode_folie and matchcode_folie != matchcode:
            aliases.add(matchcode_folie)
        if matchcode_messer and matchcode_messer != matchcode:
            aliases.add(matchcode_messer)
        if firma and firma != matchcode:
            aliases.add(firma)
        if firma_folie and firma_folie != firma:
            aliases.add(firma_folie)
        if firma_messer and firma_messer != firma:
            aliases.add(firma_messer)

        entity = BusinessEntity(
            entity_type=EntityType.CUSTOMER.value,
            name=display_name,
            display_name=firma or matchcode or display_name,
            short_name=matchcode[:50] if matchcode else None,
            street=strasse,
            street_number=haus_nr,
            postal_code=plz,
            city=ort,
            email=email,
            iban=iban if iban else None,
            bic=bic if bic else None,
            name_aliases=list(aliases),
            lexware_ids=lexware_ids,
            company_presence=companies,
            primary_customer_number=kd_nr,
            auto_detected=False,
            verified=True,  # Lexware-Import gilt als verifiziert
            confidence_score=1.0,
        )

        return entity

    async def _create_supplier_entity(
        self, name_key: str, rows: list[pd.Series]
    ) -> BusinessEntity:
        """Erstellt BusinessEntity aus Lieferantendaten."""
        def best_value(*values: Any) -> str:
            for v in values:
                if v and not is_placeholder(str(v)):
                    return str(v).strip()
            return ""

        # Beste Werte aus allen Rows sammeln
        all_matchcodes = [best_value(r.get("Matchcode", "")) for r in rows]
        all_firmas = [best_value(r.get("Firma", "")) for r in rows]

        matchcode = next((m for m in all_matchcodes if m), name_key)
        firma = next((f for f in all_firmas if f), matchcode)

        # Adresse
        strasse = best_value(*[r.get("Strasse", "") for r in rows])
        haus_nr = best_value(*[r.get("HausNr", "") for r in rows])
        plz = best_value(*[r.get("PLZ", "") for r in rows])
        ort = best_value(*[r.get("Ort", "") for r in rows])
        email = best_value(*[r.get("Email", "") for r in rows])
        iban = best_value(*[r.get("IBAN", "") for r in rows])
        bic = best_value(*[r.get("BIC", "") for r in rows])

        # Company Presence und Lexware IDs
        companies = []
        lexware_ids: dict[str, dict[str, str]] = {}

        for row in rows:
            company = row.get("Company", "")
            if company and company not in companies:
                companies.append(company)
                lexware_ids[company] = {
                    "lief_nr": best_value(row.get("Lief_Nr", "")),
                    "matchcode": best_value(row.get("Matchcode", "")),
                }

        # Name Aliases
        aliases = set()
        for mc in all_matchcodes:
            if mc and mc != matchcode:
                aliases.add(mc)
        for f in all_firmas:
            if f and f != firma:
                aliases.add(f)

        # Primäre Lieferantennummer (erste verfügbare)
        primary_lief_nr = None
        for company in ["folie", "messer"]:
            if company in lexware_ids:
                lief_nr = lexware_ids[company].get("lief_nr")
                if lief_nr:
                    primary_lief_nr = lief_nr
                    break

        entity = BusinessEntity(
            entity_type=EntityType.SUPPLIER.value,
            name=firma or matchcode or name_key,  # Lieferanten: nur Name, keine Nummer
            display_name=firma or matchcode,
            short_name=matchcode[:50] if matchcode else None,
            street=strasse,
            street_number=haus_nr,
            postal_code=plz,
            city=ort,
            email=email,
            iban=iban if iban else None,
            bic=bic if bic else None,
            name_aliases=list(aliases),
            lexware_ids=lexware_ids,
            company_presence=companies,
            primary_supplier_number=primary_lief_nr,
            auto_detected=False,
            verified=True,
            confidence_score=1.0,
        )

        return entity

    def _get_supplier_name_key(self, row: pd.Series) -> str:
        """Erstellt normalisierten Namen-Schlüssel für Lieferanten."""
        firma = str(row.get("Firma", "")).strip()
        matchcode = str(row.get("Matchcode", "")).strip()

        # Bevorzuge Firma, dann Matchcode
        name = firma if firma and not is_placeholder(firma) else matchcode
        if not name or is_placeholder(name):
            return ""

        return normalize_text(name)

    def _find_similar_name_key(
        self, name_key: str, existing_keys: set[str] | list[str]
    ) -> Optional[str]:
        """Findet ähnlichen Namen in existierenden Keys."""
        best_match = None
        best_similarity = 0.0

        for existing in existing_keys:
            sim = calculate_similarity(name_key, existing)
            if sim > self.HARMLESS_SIMILARITY_THRESHOLD and sim > best_similarity:
                best_match = existing
                best_similarity = sim

        return best_match


# ============================================================================
# FACTORY FUNCTION
# ============================================================================


def get_lexware_import_service(db: AsyncSession) -> LexwareImportService:
    """Factory-Funktion für Dependency Injection."""
    return LexwareImportService(db)
