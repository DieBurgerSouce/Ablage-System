# -*- coding: utf-8 -*-
"""Compliance Autopilot periodic tasks (F13).

Phase 12: Vollstaendige Integration mit ComplianceAutopilotService.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any

import structlog
from sqlalchemy import select

from app.core.safe_errors import safe_error_log
from app.workers.celery_app import celery_app
from app.db.session import async_session_maker
from app.db.models import Company

logger = structlog.get_logger(__name__)


@celery_app.task(name="app.workers.tasks.compliance_autopilot_tasks.run_daily_scan")
def run_daily_scan() -> dict:
    """Taeglicher Compliance-Scan aller Dokumente und Prozesse.

    Prueft:
    - GoBD-Konformitaet (Aufbewahrungsfristen, Unveraenderbarkeit)
    - GDPR-Konformitaet (Loeschfristen, Einwilligungen)
    - DLP-Policy-Verletzungen
    - Fehlende Pflichtfelder
    """
    logger.info("compliance_autopilot_daily_scan_start")
    try:
        result = asyncio.get_event_loop().run_until_complete(_run_daily_scan())
        logger.info(
            "compliance_autopilot_daily_scan_complete",
            violations_found=result.get("violations_found", 0),
        )
        return result
    except Exception as e:
        logger.error("compliance_autopilot_daily_scan_error", **safe_error_log(e))
        raise


async def _run_daily_scan() -> Dict[str, Any]:
    """Async Implementation fuer Daily Compliance Scan."""
    from app.services.compliance.autopilot_service import ComplianceAutopilotService

    total_violations = 0
    companies_scanned = 0

    async with async_session_maker() as db:
        result = await db.execute(
            select(Company.id).where(Company.is_active == True)
        )
        company_ids = [row[0] for row in result.all()]

        for company_id in company_ids:
            try:
                service = ComplianceAutopilotService()
                scan_result = await service.run_compliance_scan(company_id, db)

                total_violations += scan_result.failures
                companies_scanned += 1

                if scan_result.failures > 0:
                    logger.warning(
                        "compliance_violations_found",
                        company_id=str(company_id),
                        violations=scan_result.failures,
                        score=round(scan_result.score, 2),
                    )

            except Exception as e:
                logger.warning(
                    "compliance_scan_company_failed",
                    company_id=str(company_id),
                    **safe_error_log(e),
                )
                continue

    return {
        "status": "success",
        "companies_scanned": companies_scanned,
        "violations_found": total_violations,
    }


@celery_app.task(name="app.workers.tasks.compliance_autopilot_tasks.prepare_audit_report")
def prepare_audit_report() -> dict:
    """Bereite woechentlichen Audit-Bericht vor."""
    logger.info("compliance_autopilot_audit_report_start")
    try:
        result = asyncio.get_event_loop().run_until_complete(_prepare_audit_report())
        logger.info("compliance_autopilot_audit_report_complete")
        return result
    except Exception as e:
        logger.error("compliance_autopilot_audit_report_error", **safe_error_log(e))
        raise


async def _prepare_audit_report() -> Dict[str, Any]:
    """Async Implementation fuer Audit Report."""
    from app.services.compliance.autopilot_service import ComplianceAutopilotService

    reports_prepared = 0

    async with async_session_maker() as db:
        result = await db.execute(
            select(Company.id).where(Company.is_active == True)
        )
        company_ids = [row[0] for row in result.all()]

        # Zeitraum: letzte 7 Tage
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=7)

        for company_id in company_ids:
            try:
                service = ComplianceAutopilotService()
                package = await service.prepare_audit_package(
                    company_id=company_id,
                    start_date=start_date,
                    end_date=end_date,
                    db=db,
                )

                if package and package.document_count > 0:
                    reports_prepared += 1
                    logger.info(
                        "audit_package_prepared",
                        company_id=str(company_id),
                        documents=package.document_count,
                    )

            except Exception as e:
                logger.warning(
                    "audit_report_company_failed",
                    company_id=str(company_id),
                    **safe_error_log(e),
                )
                continue

    return {
        "status": "success",
        "reports_prepared": reports_prepared,
    }


@celery_app.task(name="app.workers.tasks.compliance_autopilot_tasks.run_gdpr_check")
def run_gdpr_check() -> dict:
    """Monatlicher DSGVO-Compliance-Check.

    Prueft:
    - Loeschfristen eingehalten
    - Verarbeitungsverzeichnis aktuell
    - Einwilligungen dokumentiert
    - Auftragsverarbeitung aktuell
    """
    logger.info("compliance_autopilot_gdpr_check_start")
    try:
        result = asyncio.get_event_loop().run_until_complete(_run_gdpr_check())
        logger.info(
            "compliance_autopilot_gdpr_check_complete",
            gdpr_issues=result.get("gdpr_issues", 0),
        )
        return result
    except Exception as e:
        logger.error("compliance_autopilot_gdpr_check_error", **safe_error_log(e))
        raise


async def _run_gdpr_check() -> Dict[str, Any]:
    """Async Implementation fuer GDPR Check."""
    from app.services.compliance.autopilot_service import ComplianceAutopilotService

    total_issues = 0
    companies_checked = 0

    async with async_session_maker() as db:
        result = await db.execute(
            select(Company.id).where(Company.is_active == True)
        )
        company_ids = [row[0] for row in result.all()]

        for company_id in company_ids:
            try:
                service = ComplianceAutopilotService()
                gdpr_result = await service.check_gdpr_compliance(company_id, db)

                total_issues += len(gdpr_result.issues)
                companies_checked += 1

                if not gdpr_result.compliant:
                    logger.warning(
                        "gdpr_issues_found",
                        company_id=str(company_id),
                        issues_count=len(gdpr_result.issues),
                        deletion_candidates=gdpr_result.deletion_candidates,
                    )

            except Exception as e:
                logger.warning(
                    "gdpr_check_company_failed",
                    company_id=str(company_id),
                    **safe_error_log(e),
                )
                continue

    return {
        "status": "success",
        "companies_checked": companies_checked,
        "gdpr_issues": total_issues,
    }
