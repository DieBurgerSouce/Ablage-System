"""Execution Layer Agents.

Autonome Agenten fuer Dokumentenverarbeitung:
- DocumentClassifierAgent: Dokumenten-Klassifikation
- OCRProcessingAgent: OCR-Verarbeitung
- MonitoringAgent: System-Ueberwachung
- QualityAssuranceAgent: Qualitaetssicherung
- TemplateExtractionAgent: Template-Extraktion
"""

from pathlib import Path

# Expose agent classes when imported
__all__ = [
    "DocumentClassifierAgent",
    "OCRProcessingAgent",
    "MonitoringAgent",
    "QualityAssuranceAgent",
    "TemplateExtractionAgent",
]
