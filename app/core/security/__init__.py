"""Security Module.

Provides secure alternatives to dangerous operations:
- SafeExpressionEvaluator: AST-based expression evaluation (replaces eval())
- SafeModuleLoader: Whitelisted module/function loading
- SensitiveDataFilter: PII masking in logs
- SafeAttributeAccess: Controlled model attribute updates
"""

from app.core.security.safe_expression_evaluator import SafeExpressionEvaluator
from app.core.security.safe_module_loader import SafeModuleLoader, safe_load_function
from app.core.security.sensitive_data_filter import sensitive_data_filter, mask_pii
from app.core.security.safe_attribute_access import safe_update, SafeAttributeAccess

__all__ = [
    "SafeExpressionEvaluator",
    "SafeModuleLoader",
    "safe_load_function",
    "sensitive_data_filter",
    "mask_pii",
    "safe_update",
    "SafeAttributeAccess",
]
