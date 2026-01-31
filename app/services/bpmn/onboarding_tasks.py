"""Customer Onboarding Workflow Task Implementations.

Service Tasks fuer den Kunden-Onboarding-Workflow.
Diese Funktionen werden von der BPMN Engine aufgerufen.
"""

from typing import Dict, Any, Optional
from uuid import UUID
from datetime import datetime, timezone
from decimal import Decimal
import secrets
import structlog

from app.core.config import settings
from app.services.email_service import EmailService

logger = structlog.get_logger(__name__)

# Singleton EmailService instance
_email_service: Optional[EmailService] = None


def get_email_service() -> EmailService:
    """Get or create EmailService singleton."""
    global _email_service
    if _email_service is None:
        _email_service = EmailService(settings)
    return _email_service


async def generate_customer_number(db, company_id: UUID) -> str:
    """Generiert eine eindeutige Kundennummer.

    Format: K{Jahr}-{5-stellige Sequenz}
    Beispiel: K2026-00001

    Args:
        db: Datenbank-Session
        company_id: Company UUID

    Returns:
        Eindeutige Kundennummer
    """
    from sqlalchemy import select, func
    from app.db.models import BusinessEntity, EntityType

    year = datetime.now().year

    # Finde hoechste Kundennummer fuer dieses Jahr
    result = await db.execute(
        select(BusinessEntity.primary_customer_number)
        .where(BusinessEntity.entity_type == EntityType.CUSTOMER.value)
        .where(BusinessEntity.primary_customer_number.like(f"K{year}-%"))
        .order_by(BusinessEntity.primary_customer_number.desc())
        .limit(1)
    )
    last_number = result.scalar_one_or_none()

    if last_number:
        try:
            # Extrahiere Sequenznummer aus "K2026-00001"
            seq = int(last_number.split("-")[1])
            next_seq = seq + 1
        except (IndexError, ValueError):
            next_seq = 1
    else:
        next_seq = 1

    return f"K{year}-{next_seq:05d}"


async def verify_customer_data(
    instance_id: str,
    variables: Dict[str, Any]
) -> Dict[str, Any]:
    """Verifiziert die Kundenstammdaten.

    Prueft Vollstaendigkeit und Plausibilitaet der Daten.

    Args:
        instance_id: BPMN Prozess-Instanz ID
        variables: Prozess-Variablen (customer_name, address, etc.)

    Returns:
        Validierungsergebnis
    """
    from app.db.session import async_session_maker
    from app.db.bpmn_models.bpmn import ProcessHistory

    customer_name = variables.get("customer_name", "")
    customer_type = variables.get("customer_type", "business")
    address = variables.get("address", {})
    contact_email = variables.get("contact_email", "")

    logger.info(
        "verifying_customer_data",
        instance_id=instance_id,
        customer_type=customer_type
    )

    validation_errors = []

    # Pflichtfeld-Pruefung
    if not customer_name:
        validation_errors.append("Kundenname fehlt")
    if not contact_email:
        validation_errors.append("E-Mail-Adresse fehlt")
    if not address.get("street"):
        validation_errors.append("Strasse fehlt")
    if not address.get("city"):
        validation_errors.append("Stadt fehlt")
    if not address.get("postal_code"):
        validation_errors.append("PLZ fehlt")

    # Geschaeftskunden-spezifische Pruefung
    if customer_type == "business":
        if not variables.get("vat_id"):
            validation_errors.append("USt-IdNr. fehlt (Geschaeftskunde)")
        if not variables.get("company_registration"):
            validation_errors.append("Handelsregisternummer fehlt")

    data_valid = len(validation_errors) == 0

    async with async_session_maker() as db:
        history = ProcessHistory(
            instance_id=UUID(instance_id),
            event_type="CUSTOMER_DATA_VERIFIED" if data_valid else "CUSTOMER_DATA_INVALID",
            message=f"Kundendaten {'validiert' if data_valid else 'unvollstaendig'}: {', '.join(validation_errors) if validation_errors else 'OK'}",
            actor_type="system",
            company_id=variables.get("company_id"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(history)
        await db.commit()

    return {
        "data_valid": data_valid,
        "validation_errors": validation_errors,
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }


async def check_credit_rating(
    instance_id: str,
    variables: Dict[str, Any]
) -> Dict[str, Any]:
    """Fuehrt eine Bonitaetspruefung durch.

    Prueft Kreditwuerdigkeit bei externen Anbietern
    (Creditreform, Buergel, SCHUFA).

    Args:
        instance_id: BPMN Prozess-Instanz ID
        variables: Prozess-Variablen

    Returns:
        Bonitaetsergebnis
    """
    from app.db.session import async_session_maker
    from app.db.bpmn_models.bpmn import ProcessHistory
    from app.services.external.credit_scoring_service import CreditScoringService, RiskLevel
    from app.services.external.creditreform_service import CreditreformService

    customer_name = variables.get("customer_name", "")
    customer_type = variables.get("customer_type", "business")
    vat_id = variables.get("vat_id", "")
    company_id_str = variables.get("company_id")
    entity_id = variables.get("entity_id")

    logger.info(
        "checking_credit_rating",
        instance_id=instance_id,
        customer_type=customer_type
    )

    credit_score = 0.0
    credit_limit = 10000.00
    risk_category = "medium"
    recommended_payment_terms = "net_14"
    check_source = "creditreform"
    warnings: list[str] = []

    async with async_session_maker() as db:
        try:
            # Initialize services
            creditreform = CreditreformService()
            scoring_service = CreditScoringService(db=db, creditreform=creditreform)

            # If entity already exists, use full scoring with internal data
            if entity_id:
                try:
                    company_id = UUID(company_id_str) if company_id_str else None
                    score_result = await scoring_service.calculate_score(
                        entity_id=UUID(entity_id),
                        company_id=company_id,
                        include_external=True
                    )
                    credit_score = score_result["total_score"]
                    credit_limit = float(score_result.get("recommended_credit_limit", 10000))
                    risk_category = score_result["risk_level"]
                    check_source = "internal_scoring"
                    warnings = score_result.get("warnings", [])

                    # Map risk level to payment terms
                    payment_terms_map = {
                        RiskLevel.MINIMAL.value: "net_60",
                        RiskLevel.LOW.value: "net_30",
                        RiskLevel.MODERATE.value: "net_14",
                        RiskLevel.ELEVATED.value: "net_7",
                        RiskLevel.HIGH.value: "prepayment",
                        RiskLevel.CRITICAL.value: "prepayment",
                    }
                    recommended_payment_terms = payment_terms_map.get(risk_category, "net_14")

                except Exception as e:
                    logger.warning(
                        "full_credit_scoring_failed",
                        instance_id=instance_id,
                        error_type=type(e).__name__
                    )
                    # Fall back to Creditreform-only
                    entity_id = None

            # New customer or fallback: use Creditreform only
            if not entity_id:
                try:
                    crefo_result = await creditreform.check_credit(
                        company_name=customer_name,
                        vat_id=vat_id if vat_id else None
                    )
                    # Convert Creditreform index (100-600) to 0-100 score
                    # 100 = best (score 100), 600 = worst (score 0)
                    credit_score = max(0, 100 - ((crefo_result.credit_index - 100) / 5))
                    credit_limit = float(crefo_result.recommended_credit_limit or 10000)
                    warnings = crefo_result.warnings + crefo_result.negative_features
                    check_source = "creditreform"

                    # Map Creditreform index to risk category
                    if crefo_result.credit_index <= 150:
                        risk_category = RiskLevel.MINIMAL.value
                        recommended_payment_terms = "net_60"
                    elif crefo_result.credit_index <= 200:
                        risk_category = RiskLevel.LOW.value
                        recommended_payment_terms = "net_30"
                    elif crefo_result.credit_index <= 250:
                        risk_category = RiskLevel.MODERATE.value
                        recommended_payment_terms = "net_14"
                    elif crefo_result.credit_index <= 350:
                        risk_category = RiskLevel.ELEVATED.value
                        recommended_payment_terms = "net_7"
                    else:
                        risk_category = RiskLevel.HIGH.value
                        recommended_payment_terms = "prepayment"

                except Exception as e:
                    logger.warning(
                        "creditreform_check_failed",
                        instance_id=instance_id,
                        error_type=type(e).__name__
                    )
                    # Use conservative defaults on API error
                    credit_score = 50.0
                    credit_limit = 5000.00
                    risk_category = RiskLevel.ELEVATED.value
                    recommended_payment_terms = "net_7"
                    check_source = "fallback"
                    warnings = ["Bonitaetspruefung konnte nicht durchgefuehrt werden"]

        except Exception as e:
            logger.exception(
                "credit_check_initialization_failed",
                instance_id=instance_id,
                error_type=type(e).__name__
            )
            # Final fallback
            credit_score = 50.0
            credit_limit = 5000.00
            risk_category = RiskLevel.ELEVATED.value
            recommended_payment_terms = "net_7"
            check_source = "fallback"
            warnings = ["Bonitaetspruefung nicht verfuegbar"]

        credit_approved = credit_score >= 40  # Threshold for approval

        # Audit entry
        history = ProcessHistory(
            instance_id=UUID(instance_id),
            event_type="CREDIT_CHECK_COMPLETED",
            message=f"Bonitaetspruefung abgeschlossen - Score: {credit_score:.1f}, Risiko: {risk_category} (Quelle: {check_source})",
            actor_type="system",
            company_id=company_id_str,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(history)
        await db.commit()

    return {
        "credit_approved": credit_approved,
        "credit_score": round(credit_score, 2),
        "credit_limit": credit_limit,
        "risk_category": risk_category,
        "recommended_payment_terms": recommended_payment_terms,
        "credit_checked_at": datetime.now(timezone.utc).isoformat(),
        "check_source": check_source,
        "warnings": warnings,
    }


async def setup_customer_account(
    instance_id: str,
    variables: Dict[str, Any]
) -> Dict[str, Any]:
    """Richtet das Kundenkonto ein.

    Erstellt Debitorennummer und BusinessEntity in der Datenbank.

    Args:
        instance_id: BPMN Prozess-Instanz ID
        variables: Prozess-Variablen

    Returns:
        Konto-Informationen inkl. customer_id
    """
    from app.db.session import async_session_maker
    from app.db.bpmn_models.bpmn import ProcessHistory
    from app.db.models import BusinessEntity, EntityType

    customer_name = variables.get("customer_name", "")
    customer_type = variables.get("customer_type", "business")
    credit_limit = variables.get("credit_limit", 5000.00)
    payment_terms = variables.get("recommended_payment_terms", "net_14")
    address = variables.get("address", {})
    contact_email = variables.get("contact_email", "")
    vat_id = variables.get("vat_id", "")
    trade_register = variables.get("company_registration", "")
    company_id_str = variables.get("company_id")

    logger.info(
        "setting_up_customer_account",
        instance_id=instance_id,
        customer_name=customer_name[:30] if customer_name else ""  # Log only first 30 chars
    )

    customer_id = None
    customer_number = None
    creation_error = None

    async with async_session_maker() as db:
        try:
            # Generiere eindeutige Kundennummer
            company_id = UUID(company_id_str) if company_id_str else None
            customer_number = await generate_customer_number(db, company_id)

            # Erstelle BusinessEntity fuer den Kunden
            entity = BusinessEntity(
                name=customer_name,
                entity_type=EntityType.CUSTOMER.value,
                primary_customer_number=customer_number,
                email=contact_email if contact_email else None,
                vat_id=vat_id if vat_id else None,
                trade_register=trade_register if trade_register else None,
                street=address.get("street"),
                postal_code=address.get("postal_code"),
                city=address.get("city"),
                country=address.get("country", "DE"),
                status="active",
                auto_detected=False,  # Manuell via Onboarding erstellt
            )

            # Setze company_id falls vorhanden (fuer Multi-Tenant-Systeme)
            if hasattr(entity, 'company_id') and company_id:
                entity.company_id = company_id

            db.add(entity)
            await db.flush()  # Generiere ID

            customer_id = str(entity.id)

            logger.info(
                "customer_entity_created",
                customer_id=customer_id,
                customer_number=customer_number
            )

        except Exception as e:
            creation_error = str(e)
            logger.exception(
                "customer_creation_failed",
                instance_id=instance_id,
                error=creation_error
            )
            # Fallback: Generiere temporaere Nummer ohne DB-Sequenz
            customer_number = f"KD-{datetime.now().strftime('%Y')}-{secrets.token_hex(4).upper()}"

        # Audit-Eintrag
        history = ProcessHistory(
            instance_id=UUID(instance_id),
            event_type="CUSTOMER_ACCOUNT_CREATED" if customer_id else "CUSTOMER_ACCOUNT_CREATION_FAILED",
            message=f"Kundenkonto erstellt - Nr: {customer_number}" if customer_id else f"Kundenerstellung fehlgeschlagen: {creation_error}",
            actor_type="system",
            company_id=company_id_str,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(history)
        await db.commit()

    # Zahlungsfrist in Tagen umrechnen
    payment_terms_days = 14  # Default
    if payment_terms == "net_30":
        payment_terms_days = 30
    elif payment_terms == "net_14":
        payment_terms_days = 14
    elif payment_terms == "prepayment":
        payment_terms_days = 0

    return {
        "account_created": customer_id is not None,
        "customer_id": customer_id,
        "customer_number": customer_number,
        "credit_limit": credit_limit,
        "payment_terms": payment_terms,
        "payment_terms_days": payment_terms_days,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "creation_error": creation_error,
    }


async def send_welcome_package(
    instance_id: str,
    variables: Dict[str, Any]
) -> Dict[str, Any]:
    """Versendet das Willkommenspaket per Email.

    Beinhaltet: Kundennummer, Kreditlimit, Zahlungsbedingungen, Kontaktdaten.

    Args:
        instance_id: BPMN Prozess-Instanz ID
        variables: Prozess-Variablen

    Returns:
        Versand-Status
    """
    from app.db.session import async_session_maker
    from app.db.bpmn_models.bpmn import ProcessHistory
    from sqlalchemy import select
    from app.db.models import BusinessEntity, Company

    customer_id = variables.get("customer_id")
    customer_number = variables.get("customer_number", "")
    contact_email = variables.get("contact_email", "")
    credit_limit = variables.get("credit_limit", 5000.00)
    payment_terms_days = variables.get("payment_terms_days", 14)
    company_id_str = variables.get("company_id")

    logger.info(
        "sending_welcome_package",
        instance_id=instance_id,
        customer_number=customer_number
    )

    email_sent = False
    email_error = None

    async with async_session_maker() as db:
        try:
            # Lade Entity und Company fuer Email
            entity = None
            company = None

            if customer_id:
                entity_result = await db.execute(
                    select(BusinessEntity).where(BusinessEntity.id == UUID(customer_id))
                )
                entity = entity_result.scalar_one_or_none()

            if company_id_str:
                company_result = await db.execute(
                    select(Company).where(Company.id == UUID(company_id_str))
                )
                company = company_result.scalar_one_or_none()

            # Sende Welcome-Email
            if entity and company and (entity.email or contact_email):
                # Setze Email-Adresse falls nicht in Entity
                if not entity.email and contact_email:
                    entity.email = contact_email

                email_service = get_email_service()
                result = await email_service.send_welcome_package(
                    entity=entity,
                    company=company,
                    credit_limit=Decimal(str(credit_limit)) if credit_limit else None,
                    payment_terms_days=payment_terms_days
                )
                email_sent = result.success
                if not result.success:
                    email_error = result.error_message
                    logger.warning(
                        "welcome_email_failed",
                        customer_number=customer_number,
                        error=email_error
                    )
            else:
                email_error = "Missing entity, company, or email address"
                logger.warning(
                    "welcome_email_skipped",
                    customer_number=customer_number,
                    reason=email_error
                )

        except Exception as e:
            email_error = str(e)
            logger.exception(
                "welcome_email_exception",
                customer_number=customer_number,
                error=email_error
            )

        # Audit-Eintrag
        history = ProcessHistory(
            instance_id=UUID(instance_id),
            event_type="WELCOME_PACKAGE_SENT" if email_sent else "WELCOME_PACKAGE_FAILED",
            message=f"Willkommenspaket {'versendet' if email_sent else 'fehlgeschlagen'}" + (f": {email_error}" if email_error else ""),
            actor_type="system",
            company_id=company_id_str,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(history)
        await db.commit()

    return {
        "welcome_sent": email_sent,
        "sent_to": contact_email or (entity.email if entity else ""),
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "package_contents": ["kundennummer", "kreditlimit", "zahlungsbedingungen", "kontaktdaten"],
        "email_error": email_error,
    }


async def assign_account_manager(
    instance_id: str,
    variables: Dict[str, Any]
) -> Dict[str, Any]:
    """Weist einen Kundenbetreuer zu.

    Basierend auf Region, Branche oder Umsatzpotential.
    Intelligente Zuweisung mit Workload-Balancing.

    Args:
        instance_id: BPMN Prozess-Instanz ID
        variables: Prozess-Variablen

    Returns:
        Betreuer-Zuweisung
    """
    from app.db.session import async_session_maker
    from app.db.bpmn_models.bpmn import ProcessHistory
    from app.db.models import User, Role, BusinessEntity, user_roles
    from sqlalchemy import select, func, and_, or_
    from sqlalchemy.orm import selectinload

    customer_type = variables.get("customer_type", "business")
    credit_limit = variables.get("credit_limit", 0)
    address = variables.get("address", {})
    region = address.get("region", "")
    postal_code = address.get("postal_code", "")
    company_id_str = variables.get("company_id")
    customer_id = variables.get("customer_id")

    logger.info(
        "assigning_account_manager",
        instance_id=instance_id,
        region=region or postal_code[:2] if postal_code else "unknown"
    )

    # Determine manager role based on credit limit (key account threshold: 50000 EUR)
    is_key_account = credit_limit >= 50000
    target_role_name = "key_account_manager" if is_key_account else "account_manager"

    manager_id: Optional[str] = None
    manager_name = "Automatische Zuweisung ausstehend"
    manager_type = target_role_name
    assignment_method = "fallback"

    async with async_session_maker() as db:
        try:
            company_id = UUID(company_id_str) if company_id_str else None

            # Build query to find available managers with their workload
            # Step 1: Find role ID for target role
            role_result = await db.execute(
                select(Role.id).where(
                    and_(
                        Role.name == target_role_name,
                        Role.is_active == True
                    )
                )
            )
            target_role_id = role_result.scalar_one_or_none()

            # Fallback to general account_manager if key_account_manager not found
            if not target_role_id and is_key_account:
                role_result = await db.execute(
                    select(Role.id).where(
                        and_(
                            Role.name == "account_manager",
                            Role.is_active == True
                        )
                    )
                )
                target_role_id = role_result.scalar_one_or_none()
                if target_role_id:
                    target_role_name = "account_manager"
                    manager_type = "account_manager"

            if target_role_id:
                # Step 2: Find users with this role, counting their active customers
                # Subquery: count active entities per user (assuming assigned_manager_id or created_by)
                customer_count_subquery = (
                    select(
                        BusinessEntity.created_by_id.label("manager_id"),
                        func.count(BusinessEntity.id).label("customer_count")
                    )
                    .where(
                        and_(
                            BusinessEntity.is_active == True,
                            BusinessEntity.deleted_at.is_(None),
                            BusinessEntity.entity_type == "customer"
                        )
                    )
                    .group_by(BusinessEntity.created_by_id)
                    .subquery()
                )

                # Find eligible managers
                managers_query = (
                    select(
                        User,
                        func.coalesce(customer_count_subquery.c.customer_count, 0).label("workload")
                    )
                    .join(user_roles, user_roles.c.user_id == User.id)
                    .outerjoin(
                        customer_count_subquery,
                        customer_count_subquery.c.manager_id == User.id
                    )
                    .where(
                        and_(
                            user_roles.c.role_id == target_role_id,
                            User.is_active == True,
                            or_(
                                User.access_until.is_(None),
                                User.access_until > datetime.now(timezone.utc)
                            )
                        )
                    )
                    .order_by(
                        func.coalesce(customer_count_subquery.c.customer_count, 0).asc()  # Least loaded first
                    )
                )

                # If we have a postal code, try to find a regional match first
                # (This assumes managers might have regions stored in preferences or access_scope)
                result = await db.execute(managers_query)
                managers = result.all()

                if managers:
                    # Select the manager with lowest workload
                    selected_manager, workload = managers[0]
                    manager_name = selected_manager.full_name or selected_manager.username
                    manager_id = str(selected_manager.id)
                    assignment_method = "workload_balanced"

                    logger.info(
                        "manager_selected",
                        instance_id=instance_id,
                        manager_id=manager_id,
                        workload=workload,
                        candidates=len(managers)
                    )

                    # If customer_id exists, update the entity's created_by (for tracking purposes)
                    if customer_id:
                        try:
                            entity_result = await db.execute(
                                select(BusinessEntity).where(BusinessEntity.id == UUID(customer_id))
                            )
                            entity = entity_result.scalar_one_or_none()
                            if entity:
                                entity.created_by_id = selected_manager.id
                        except Exception as e:
                            logger.warning(
                                "entity_manager_update_failed",
                                customer_id=customer_id,
                                error_type=type(e).__name__
                            )
                else:
                    logger.warning(
                        "no_managers_found",
                        instance_id=instance_id,
                        target_role=target_role_name
                    )
            else:
                logger.warning(
                    "manager_role_not_found",
                    instance_id=instance_id,
                    target_role=target_role_name
                )

        except Exception as e:
            logger.exception(
                "manager_assignment_failed",
                instance_id=instance_id,
                error_type=type(e).__name__
            )

        # Audit entry
        history = ProcessHistory(
            instance_id=UUID(instance_id),
            event_type="ACCOUNT_MANAGER_ASSIGNED",
            message=f"Kundenbetreuer zugewiesen: {manager_name} ({assignment_method})",
            actor_type="system",
            company_id=company_id_str,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(history)
        await db.commit()

    return {
        "manager_assigned": manager_id is not None,
        "manager_id": manager_id,
        "manager_name": manager_name,
        "manager_type": manager_type,
        "assignment_method": assignment_method,
        "is_key_account": is_key_account,
        "assigned_at": datetime.now(timezone.utc).isoformat(),
    }


async def complete_onboarding(
    instance_id: str,
    variables: Dict[str, Any]
) -> Dict[str, Any]:
    """Schliesst das Onboarding ab.

    Aktiviert den Kunden fuer den Geschaeftsbetrieb.

    Args:
        instance_id: BPMN Prozess-Instanz ID
        variables: Prozess-Variablen

    Returns:
        Abschluss-Informationen
    """
    from app.db.session import async_session_maker
    from app.db.bpmn_models.bpmn import ProcessHistory
    from sqlalchemy import select
    from app.db.models import BusinessEntity

    customer_id = variables.get("customer_id")
    customer_number = variables.get("customer_number", "")
    credit_approved = variables.get("credit_approved", False)
    company_id_str = variables.get("company_id")

    logger.info(
        "completing_onboarding",
        instance_id=instance_id,
        customer_number=customer_number
    )

    # Onboarding-Status
    onboarding_status = "active" if credit_approved else "limited"
    status_updated = False

    async with async_session_maker() as db:
        try:
            # Kunde aktivieren
            if customer_id:
                entity_result = await db.execute(
                    select(BusinessEntity).where(BusinessEntity.id == UUID(customer_id))
                )
                entity = entity_result.scalar_one_or_none()

                if entity:
                    entity.status = onboarding_status
                    status_updated = True
                    logger.info(
                        "customer_status_updated",
                        customer_id=customer_id,
                        status=onboarding_status
                    )
        except Exception as e:
            logger.exception(
                "customer_status_update_failed",
                customer_id=customer_id,
                error=str(e)
            )

        history = ProcessHistory(
            instance_id=UUID(instance_id),
            event_type="ONBOARDING_COMPLETED",
            message=f"Onboarding abgeschlossen - Status: {onboarding_status}",
            actor_type="system",
            company_id=company_id_str,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(history)
        await db.commit()

    return {
        "onboarding_completed": True,
        "customer_status": onboarding_status,
        "customer_number": customer_number,
        "customer_id": customer_id,
        "status_updated": status_updated,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }


def calculate_onboarding_priority(
    customer_type: str,
    expected_revenue: float | None = None
) -> str:
    """Berechnet die Onboarding-Prioritaet.

    Args:
        customer_type: 'business' oder 'private'
        expected_revenue: Erwarteter Jahresumsatz

    Returns:
        Prioritaet: 'high', 'medium', 'low'
    """
    if customer_type == "business":
        if expected_revenue and expected_revenue >= 100000:
            return "high"
        elif expected_revenue and expected_revenue >= 25000:
            return "medium"
    return "low"
