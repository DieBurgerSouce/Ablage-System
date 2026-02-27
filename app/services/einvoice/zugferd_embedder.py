# -*- coding: utf-8 -*-
"""
ZUGFeRD Embedder - PDF/A-3 XML Embedding.

Embeddet ZUGFeRD/Factur-X XML in PDF/A-3 konforme PDFs.

Unterstützte Profile:
- MINIMUM, BASIC, BASIC_WL, EN16931, EXTENDED, XRECHNUNG

Referenz: ZUGFeRD 2.3.3 / Factur-X 1.0 / PDF/A-3 (ISO 19005-3)
"""

import hashlib
import io
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional, Tuple

import structlog

from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


class ZUGFeRDProfile(str, Enum):
    """ZUGFeRD/Factur-X Profile."""
    MINIMUM = "MINIMUM"
    BASIC = "BASIC"
    BASIC_WL = "BASIC_WL"
    EN16931 = "EN16931"
    EXTENDED = "EXTENDED"
    XRECHNUNG = "XRECHNUNG"


# Profile zu Relationship-Type Mapping (PDF/A-3)
PROFILE_RELATIONSHIP = {
    ZUGFeRDProfile.MINIMUM: "Data",
    ZUGFeRDProfile.BASIC: "Data",
    ZUGFeRDProfile.BASIC_WL: "Data",
    ZUGFeRDProfile.EN16931: "Alternative",
    ZUGFeRDProfile.EXTENDED: "Alternative",
    ZUGFeRDProfile.XRECHNUNG: "Alternative",
}

# Attachment Filename per Standard
FACTURX_FILENAME = "factur-x.xml"
ZUGFERD_FILENAME = "zugferd-invoice.xml"


class ZUGFeRDEmbedder:
    """
    Embeddet ZUGFeRD XML in PDF/A-3 konforme PDFs.

    Verwendung:
        embedder = ZUGFeRDEmbedder()

        # XML in bestehendes PDF embedden
        pdf_bytes = embedder.embed_xml_in_pdf(pdf_content, xml_content, profile)

        # XML aus PDF extrahieren
        xml_content = embedder.extract_xml_from_pdf(pdf_content)

        # PDF auf PDF/A-3 Konformität prüfen
        is_valid = embedder.check_pdfa3_compliance(pdf_content)
    """

    def __init__(self) -> None:
        """Initialisiere Embedder mit verfügbaren Backends."""
        self._backend: Optional[str] = None
        self._detect_backend()

    def _detect_backend(self) -> None:
        """Erkennt verfügbares PDF-Backend (PyMuPDF oder pikepdf)."""
        try:
            import fitz  # PyMuPDF
            self._backend = "pymupdf"
            logger.info("zugferd_embedder_backend", backend="pymupdf")
        except ImportError:
            try:
                import pikepdf
                self._backend = "pikepdf"
                logger.info("zugferd_embedder_backend", backend="pikepdf")
            except ImportError:
                self._backend = None
                logger.warning(
                    "zugferd_embedder_no_backend",
                    message="Weder PyMuPDF noch pikepdf installiert"
                )

    @property
    def available(self) -> bool:
        """Prüft ob ein PDF-Backend verfügbar ist."""
        return self._backend is not None

    def embed_xml_in_pdf(
        self,
        pdf_content: bytes,
        xml_content: str,
        profile: ZUGFeRDProfile = ZUGFeRDProfile.EN16931,
        use_facturx_name: bool = True
    ) -> Tuple[bytes, dict]:
        """
        Embeddet ZUGFeRD XML in ein PDF als PDF/A-3 Attachment.

        Args:
            pdf_content: Original-PDF als Bytes
            xml_content: ZUGFeRD XML als String
            profile: ZUGFeRD-Profil (bestimmt Relationship-Type)
            use_facturx_name: True für factur-x.xml, False für zugferd-invoice.xml

        Returns:
            Tuple aus:
            - bytes: PDF mit eingebettetem XML
            - dict: Metadaten (xml_hash, profile, filename)

        Raises:
            RuntimeError: Wenn kein Backend verfügbar
            ValueError: Bei ungültigem PDF oder XML
        """
        if not self.available:
            raise RuntimeError(
                "Kein PDF-Backend verfügbar. "
                "Installieren Sie PyMuPDF (pip install pymupdf) "
                "oder pikepdf (pip install pikepdf)."
            )

        # XML Validierung
        if not xml_content or not xml_content.strip():
            raise ValueError("XML-Inhalt darf nicht leer sein")

        # XML Hash für Integrität
        xml_bytes = xml_content.encode("utf-8")
        xml_hash = hashlib.sha256(xml_bytes).hexdigest()

        # Attachment-Filename
        attachment_filename = FACTURX_FILENAME if use_facturx_name else ZUGFERD_FILENAME

        # Relationship-Type basierend auf Profil
        relationship = PROFILE_RELATIONSHIP.get(profile, "Alternative")

        if self._backend == "pymupdf":
            result_pdf = self._embed_with_pymupdf(
                pdf_content, xml_bytes, attachment_filename, relationship, profile
            )
        else:
            result_pdf = self._embed_with_pikepdf(
                pdf_content, xml_bytes, attachment_filename, relationship, profile
            )

        metadata = {
            "xml_hash": xml_hash,
            "profile": profile.value,
            "filename": attachment_filename,
            "relationship": relationship,
            "embedded_at": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            "zugferd_xml_embedded",
            profile=profile.value,
            filename=attachment_filename,
            xml_size=len(xml_bytes),
        )

        return result_pdf, metadata

    def _embed_with_pymupdf(
        self,
        pdf_content: bytes,
        xml_bytes: bytes,
        filename: str,
        relationship: str,
        profile: ZUGFeRDProfile
    ) -> bytes:
        """Embeddet XML mit PyMuPDF (fitz)."""
        import fitz

        try:
            # PDF öffnen
            doc = fitz.open(stream=pdf_content, filetype="pdf")

            # XML als Embedded File hinzufuegen
            # PyMuPDF verwendet embfile_add für Attachments
            doc.embfile_add(
                name=filename,
                buffer_=xml_bytes,
                filename=filename,
                ufilename=filename,
                desc=f"ZUGFeRD {profile.value} Invoice Data"
            )

            # PDF/A-3 Metadaten setzen (XMP)
            xmp_metadata = self._create_xmp_metadata(profile, filename, relationship)
            doc.set_xml_metadata(xmp_metadata)

            # Als Bytes exportieren
            output = io.BytesIO()
            doc.save(output, garbage=4, deflate=True)
            doc.close()

            return output.getvalue()

        except Exception as e:
            logger.error("pymupdf_embed_failed", **safe_error_log(e))
            raise ValueError(f"PDF-Embedding fehlgeschlagen: {type(e).__name__}")

    def _embed_with_pikepdf(
        self,
        pdf_content: bytes,
        xml_bytes: bytes,
        filename: str,
        relationship: str,
        profile: ZUGFeRDProfile
    ) -> bytes:
        """Embeddet XML mit pikepdf."""
        import pikepdf
        from pikepdf import AttachedFileSpec, Name

        try:
            # PDF öffnen
            pdf = pikepdf.open(io.BytesIO(pdf_content))

            # Embedded File Stream erstellen
            embedded_file = pikepdf.Stream(pdf, xml_bytes)
            embedded_file[Name.Type] = Name.EmbeddedFile
            embedded_file[Name.Subtype] = Name("/text/xml")

            # File Specification erstellen
            filespec = AttachedFileSpec.from_filepath(
                pdf,
                io.BytesIO(xml_bytes),
                description=f"ZUGFeRD {profile.value} Invoice Data"
            )

            # Alternative: Manuelle FileSpec erstellen
            filespec_dict = pikepdf.Dictionary({
                Name.Type: Name.Filespec,
                Name.F: filename,
                Name.UF: filename,
                Name.Desc: f"ZUGFeRD {profile.value} Invoice Data",
                Name.AFRelationship: Name(f"/{relationship}"),
                Name.EF: pikepdf.Dictionary({
                    Name.F: embedded_file,
                    Name.UF: embedded_file,
                }),
            })

            # Embedded Files Name Tree
            if Name.Names not in pdf.Root:
                pdf.Root[Name.Names] = pikepdf.Dictionary()
            if Name.EmbeddedFiles not in pdf.Root[Name.Names]:
                pdf.Root[Name.Names][Name.EmbeddedFiles] = pikepdf.Dictionary()

            names_dict = pdf.Root[Name.Names][Name.EmbeddedFiles]
            if Name.Names not in names_dict:
                names_dict[Name.Names] = pikepdf.Array()

            # Attachment hinzufuegen
            names_array = list(names_dict[Name.Names])
            names_array.extend([filename, filespec_dict])
            names_dict[Name.Names] = pikepdf.Array(names_array)

            # AF Array (Associated Files) für PDF/A-3
            if Name.AF not in pdf.Root:
                pdf.Root[Name.AF] = pikepdf.Array()
            af_array = list(pdf.Root[Name.AF])
            af_array.append(filespec_dict)
            pdf.Root[Name.AF] = pikepdf.Array(af_array)

            # Als Bytes exportieren
            output = io.BytesIO()
            pdf.save(output)
            pdf.close()

            return output.getvalue()

        except Exception as e:
            logger.error("pikepdf_embed_failed", **safe_error_log(e))
            raise ValueError(f"PDF-Embedding fehlgeschlagen: {type(e).__name__}")

    def extract_xml_from_pdf(self, pdf_content: bytes) -> Optional[str]:
        """
        Extrahiert eingebettetes ZUGFeRD XML aus PDF.

        Args:
            pdf_content: PDF als Bytes

        Returns:
            XML-Inhalt als String oder None wenn nicht gefunden

        Raises:
            RuntimeError: Wenn kein Backend verfügbar
            ValueError: Bei ungültigem PDF
        """
        if not self.available:
            raise RuntimeError("Kein PDF-Backend verfügbar")

        if self._backend == "pymupdf":
            return self._extract_with_pymupdf(pdf_content)
        else:
            return self._extract_with_pikepdf(pdf_content)

    def _extract_with_pymupdf(self, pdf_content: bytes) -> Optional[str]:
        """Extrahiert XML mit PyMuPDF."""
        import fitz

        try:
            doc = fitz.open(stream=pdf_content, filetype="pdf")

            # Nach bekannten Dateinamen suchen
            for name in [FACTURX_FILENAME, ZUGFERD_FILENAME]:
                try:
                    # embfile_get gibt Dict zurück mit 'content' key
                    file_data = doc.embfile_get(name)
                    if file_data and "content" in file_data:
                        doc.close()
                        return file_data["content"].decode("utf-8")
                except Exception:
                    continue

            # Fallback: Alle Attachments durchsuchen
            count = doc.embfile_count()
            for i in range(count):
                info = doc.embfile_info(i)
                if info and info.get("name", "").endswith(".xml"):
                    file_data = doc.embfile_get(info["name"])
                    if file_data and "content" in file_data:
                        doc.close()
                        return file_data["content"].decode("utf-8")

            doc.close()
            return None

        except Exception as e:
            logger.warning("pymupdf_extract_failed", **safe_error_log(e))
            return None

    def _extract_with_pikepdf(self, pdf_content: bytes) -> Optional[str]:
        """Extrahiert XML mit pikepdf."""
        import pikepdf
        from pikepdf import Name

        try:
            pdf = pikepdf.open(io.BytesIO(pdf_content))

            # Embedded Files suchen
            if Name.Names in pdf.Root:
                names = pdf.Root[Name.Names]
                if Name.EmbeddedFiles in names:
                    ef = names[Name.EmbeddedFiles]
                    if Name.Names in ef:
                        names_array = ef[Name.Names]
                        # Names Array ist [name, filespec, name, filespec, ...]
                        for i in range(0, len(names_array), 2):
                            name = str(names_array[i])
                            if name in [FACTURX_FILENAME, ZUGFERD_FILENAME] or name.endswith(".xml"):
                                filespec = names_array[i + 1]
                                if Name.EF in filespec and Name.F in filespec[Name.EF]:
                                    stream = filespec[Name.EF][Name.F]
                                    xml_bytes = bytes(stream.get_stream_buffer())
                                    pdf.close()
                                    return xml_bytes.decode("utf-8")

            pdf.close()
            return None

        except Exception as e:
            logger.warning("pikepdf_extract_failed", **safe_error_log(e))
            return None

    def check_pdfa3_compliance(self, pdf_content: bytes) -> dict:
        """
        Prüft PDF auf PDF/A-3 Konformität (vereinfacht).

        Args:
            pdf_content: PDF als Bytes

        Returns:
            Dict mit Prüfergebnis:
            - compliant: True/False
            - has_embedded_files: True/False
            - embedded_files: Liste der Dateinamen
            - issues: Liste von Problemen
        """
        result = {
            "compliant": False,
            "has_embedded_files": False,
            "embedded_files": [],
            "issues": [],
        }

        if not self.available:
            result["issues"].append("Kein PDF-Backend verfügbar")
            return result

        if self._backend == "pymupdf":
            return self._check_with_pymupdf(pdf_content, result)
        else:
            return self._check_with_pikepdf(pdf_content, result)

    def _check_with_pymupdf(self, pdf_content: bytes, result: dict) -> dict:
        """Prüft Konformität mit PyMuPDF."""
        import fitz

        try:
            doc = fitz.open(stream=pdf_content, filetype="pdf")

            # Embedded Files zaehlen
            count = doc.embfile_count()
            if count > 0:
                result["has_embedded_files"] = True
                for i in range(count):
                    info = doc.embfile_info(i)
                    if info:
                        result["embedded_files"].append(info.get("name", f"file_{i}"))

            # XMP Metadaten prüfen (PDF/A Indikator)
            xmp = doc.xref_xml_metadata()
            if xmp:
                if "pdfaid:part" in xmp.lower() or "pdfa:part" in xmp.lower():
                    if "3" in xmp:
                        result["compliant"] = True
                else:
                    result["issues"].append("Keine PDF/A Metadaten gefunden")
            else:
                result["issues"].append("Keine XMP Metadaten")

            doc.close()

        except Exception as e:
            result["issues"].append(f"Prüfung fehlgeschlagen: {type(e).__name__}")
            logger.warning("pdfa3_check_failed", **safe_error_log(e))

        return result

    def _check_with_pikepdf(self, pdf_content: bytes, result: dict) -> dict:
        """Prüft Konformität mit pikepdf."""
        import pikepdf
        from pikepdf import Name

        try:
            pdf = pikepdf.open(io.BytesIO(pdf_content))

            # Embedded Files suchen
            if Name.Names in pdf.Root:
                names = pdf.Root[Name.Names]
                if Name.EmbeddedFiles in names:
                    ef = names[Name.EmbeddedFiles]
                    if Name.Names in ef:
                        result["has_embedded_files"] = True
                        names_array = ef[Name.Names]
                        for i in range(0, len(names_array), 2):
                            result["embedded_files"].append(str(names_array[i]))

            # XMP Metadaten prüfen
            if pdf.Root.get(Name.Metadata):
                xmp_stream = pdf.Root[Name.Metadata]
                xmp_data = bytes(xmp_stream.get_stream_buffer()).decode("utf-8", errors="ignore")
                if "pdfaid:part" in xmp_data.lower():
                    if ">3<" in xmp_data or "'3'" in xmp_data:
                        result["compliant"] = True
                else:
                    result["issues"].append("Keine PDF/A Metadaten")
            else:
                result["issues"].append("Keine XMP Metadaten")

            pdf.close()

        except Exception as e:
            result["issues"].append(f"Prüfung fehlgeschlagen: {type(e).__name__}")
            logger.warning("pdfa3_check_failed", **safe_error_log(e))

        return result

    def _create_xmp_metadata(
        self,
        profile: ZUGFeRDProfile,
        filename: str,
        relationship: str
    ) -> str:
        """Erstellt XMP Metadaten für PDF/A-3 mit ZUGFeRD Extension."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

        # Profile URN
        profile_urn = {
            ZUGFeRDProfile.MINIMUM: "urn:factur-x.eu:1p0:minimum",
            ZUGFeRDProfile.BASIC: "urn:factur-x.eu:1p0:basic",
            ZUGFeRDProfile.BASIC_WL: "urn:factur-x.eu:1p0:basicwl",
            ZUGFeRDProfile.EN16931: "urn:cen.eu:en16931:2017",
            ZUGFeRDProfile.EXTENDED: "urn:factur-x.eu:1p0:extended",
            ZUGFeRDProfile.XRECHNUNG: "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf:spec:XRechnung:3.0",
        }.get(profile, "urn:cen.eu:en16931:2017")

        xmp = f'''<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
    <rdf:Description rdf:about=""
        xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/"
        xmlns:fx="urn:factur-x:pdfa:CrossIndustryDocument:invoice:1p0#">
      <pdfaid:part>3</pdfaid:part>
      <pdfaid:conformance>B</pdfaid:conformance>
      <fx:DocumentType>INVOICE</fx:DocumentType>
      <fx:DocumentFileName>{filename}</fx:DocumentFileName>
      <fx:Version>1.0</fx:Version>
      <fx:ConformanceLevel>{profile.value}</fx:ConformanceLevel>
    </rdf:Description>
    <rdf:Description rdf:about=""
        xmlns:xmp="http://ns.adobe.com/xap/1.0/">
      <xmp:CreateDate>{now}</xmp:CreateDate>
      <xmp:ModifyDate>{now}</xmp:ModifyDate>
      <xmp:CreatorTool>Ablage-System ZUGFeRD Embedder</xmp:CreatorTool>
    </rdf:Description>
    <rdf:Description rdf:about=""
        xmlns:dc="http://purl.org/dc/elements/1.1/">
      <dc:format>application/pdf</dc:format>
      <dc:title>
        <rdf:Alt>
          <rdf:li xml:lang="x-default">ZUGFeRD Invoice</rdf:li>
        </rdf:Alt>
      </dc:title>
    </rdf:Description>
    <rdf:Description rdf:about=""
        xmlns:pdfaExtension="http://www.aiim.org/pdfa/ns/extension/"
        xmlns:pdfaSchema="http://www.aiim.org/pdfa/ns/schema#"
        xmlns:pdfaProperty="http://www.aiim.org/pdfa/ns/property#">
      <pdfaExtension:schemas>
        <rdf:Bag>
          <rdf:li>
            <rdf:Description>
              <pdfaSchema:schema>Factur-X PDFA Extension Schema</pdfaSchema:schema>
              <pdfaSchema:namespaceURI>urn:factur-x:pdfa:CrossIndustryDocument:invoice:1p0#</pdfaSchema:namespaceURI>
              <pdfaSchema:prefix>fx</pdfaSchema:prefix>
              <pdfaSchema:property>
                <rdf:Seq>
                  <rdf:li>
                    <rdf:Description>
                      <pdfaProperty:name>DocumentFileName</pdfaProperty:name>
                      <pdfaProperty:valueType>Text</pdfaProperty:valueType>
                      <pdfaProperty:category>external</pdfaProperty:category>
                      <pdfaProperty:description>Name of embedded XML invoice file</pdfaProperty:description>
                    </rdf:Description>
                  </rdf:li>
                  <rdf:li>
                    <rdf:Description>
                      <pdfaProperty:name>DocumentType</pdfaProperty:name>
                      <pdfaProperty:valueType>Text</pdfaProperty:valueType>
                      <pdfaProperty:category>external</pdfaProperty:category>
                      <pdfaProperty:description>INVOICE</pdfaProperty:description>
                    </rdf:Description>
                  </rdf:li>
                  <rdf:li>
                    <rdf:Description>
                      <pdfaProperty:name>Version</pdfaProperty:name>
                      <pdfaProperty:valueType>Text</pdfaProperty:valueType>
                      <pdfaProperty:category>external</pdfaProperty:category>
                      <pdfaProperty:description>Version of Factur-X</pdfaProperty:description>
                    </rdf:Description>
                  </rdf:li>
                  <rdf:li>
                    <rdf:Description>
                      <pdfaProperty:name>ConformanceLevel</pdfaProperty:name>
                      <pdfaProperty:valueType>Text</pdfaProperty:valueType>
                      <pdfaProperty:category>external</pdfaProperty:category>
                      <pdfaProperty:description>Conformance level</pdfaProperty:description>
                    </rdf:Description>
                  </rdf:li>
                </rdf:Seq>
              </pdfaSchema:property>
            </rdf:Description>
          </rdf:li>
        </rdf:Bag>
      </pdfaExtension:schemas>
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>'''

        return xmp


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

_zugferd_embedder_instance: Optional[ZUGFeRDEmbedder] = None


def get_zugferd_embedder() -> ZUGFeRDEmbedder:
    """
    Factory-Funktion für ZUGFeRDEmbedder (Singleton).

    Returns:
        ZUGFeRDEmbedder: Globale Embedder-Instanz
    """
    global _zugferd_embedder_instance
    if _zugferd_embedder_instance is None:
        _zugferd_embedder_instance = ZUGFeRDEmbedder()
    return _zugferd_embedder_instance
