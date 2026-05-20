"""Portfolio Services - DEPRECATED.

Dieses Modul ist deprecated. Verwende stattdessen:
- app.services.privat.portfolio_service.PortfolioService
- app.services.privat.financial_goals_service.FinancialGoalsService
"""

# Re-export from new location for backwards compatibility
from app.services.privat.financial_goals_service import (
    FinancialGoalsService,
    FinancialGoal,
    GoalProgress,
)

__all__ = [
    "FinancialGoalsService",
    "FinancialGoal",
    "GoalProgress",
]
