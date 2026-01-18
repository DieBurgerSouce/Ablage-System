"""Portfolio Services fuer Enterprise Features.

Dieses Modul enthaelt die Portfolio-Services:
- PortfolioService: Vermoegensuebersicht und Snapshots (DEPRECATED - missing model)
- FinancialGoalsService: Finanzielle Ziele und Tracking
"""

# PortfolioService is DEPRECATED - uses missing PrivatBankAccount model
# Use app.services.privat.portfolio_service.PortfolioService instead
try:
    from app.services.portfolio.portfolio_service import (
        PortfolioService,
        PortfolioSnapshot,
    )
    _PORTFOLIO_SERVICE_AVAILABLE = True
except ImportError:
    PortfolioService = None  # type: ignore
    PortfolioSnapshot = None  # type: ignore
    _PORTFOLIO_SERVICE_AVAILABLE = False

from app.services.portfolio.financial_goals_service import (
    FinancialGoalsService,
    FinancialGoal,
    GoalProgress,
)

__all__ = [
    "FinancialGoalsService",
    "FinancialGoal",
    "GoalProgress",
]

# Only export PortfolioService if available
if _PORTFOLIO_SERVICE_AVAILABLE:
    __all__.extend(["PortfolioService", "PortfolioSnapshot"])
