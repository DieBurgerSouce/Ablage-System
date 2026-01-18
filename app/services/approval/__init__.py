"""Approval System Services.

Enterprise Feature: Vollstaendiges Genehmigungssystem mit:
- Rule-basiertem Routing
- Multi-Step Approval Chains
- Eskalation und Delegation
- Integration mit Workflows
- Auto-Approval fuer Niedrig-Risiko-Dokumente
"""

from app.services.approval.approval_service import ApprovalService
from app.services.approval.approval_rule_service import ApprovalRuleService
from app.services.approval.auto_approval_service import (
    AutoApprovalService,
    AutoApprovalConfig,
    AutoApprovalRule,
    AutoApprovalResult,
    AutoApprovalDecision,
    AutoApprovalReason,
    EntityTrustScore,
    get_auto_approval_service,
)

__all__ = [
    "ApprovalService",
    "ApprovalRuleService",
    "AutoApprovalService",
    "AutoApprovalConfig",
    "AutoApprovalRule",
    "AutoApprovalResult",
    "AutoApprovalDecision",
    "AutoApprovalReason",
    "EntityTrustScore",
    "get_auto_approval_service",
]
