"""Safe Expression Evaluator.

AST-based expression evaluator that replaces dangerous eval() calls.
Only allows whitelisted operators and functions for BPMN expressions.

Security Features:
- No arbitrary code execution (CWE-94, CWE-95)
- Whitelist-based operators and functions
- Expression length limits
- Recursion depth limits
- No access to builtins or module imports

Example:
    evaluator = SafeExpressionEvaluator()
    result = evaluator.evaluate("amount > 1000 and approved == True", {"amount": 1500, "approved": True})
    # Returns: True
"""

import ast
import operator
from decimal import Decimal
from typing import Any, Dict, Optional, Union, Callable
import structlog
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)

# Configuration
MAX_EXPRESSION_LENGTH = 500
MAX_RECURSION_DEPTH = 10
MAX_STRING_LENGTH = 10000

# Type alias for values in expressions
ExpressionValue = Union[int, float, Decimal, str, bool, None, list, dict]


class ExpressionSecurityError(Exception):
    """Raised when expression contains disallowed operations."""
    pass


class ExpressionEvaluationError(Exception):
    """Raised when expression evaluation fails."""
    pass


class SafeExpressionEvaluator:
    """AST-based safe expression evaluator.

    Replaces eval() with a secure alternative that only allows
    whitelisted operators and functions.

    Attributes:
        ALLOWED_OPERATORS: Mapping of AST operator types to functions
        ALLOWED_FUNCTIONS: Set of allowed builtin function names
        ALLOWED_COMPARISONS: Mapping of AST comparison types to functions
    """

    # Allowed binary operators
    ALLOWED_OPERATORS: Dict[type, Callable[[Any, Any], Any]] = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
    }

    # Allowed comparison operators
    ALLOWED_COMPARISONS: Dict[type, Callable[[Any, Any], bool]] = {
        ast.Eq: operator.eq,
        ast.NotEq: operator.ne,
        ast.Lt: operator.lt,
        ast.LtE: operator.le,
        ast.Gt: operator.gt,
        ast.GtE: operator.ge,
        ast.Is: operator.is_,
        ast.IsNot: operator.is_not,
        ast.In: lambda x, y: x in y,
        ast.NotIn: lambda x, y: x not in y,
    }

    # Allowed unary operators
    ALLOWED_UNARY: Dict[type, Callable[[Any], Any]] = {
        ast.UAdd: operator.pos,
        ast.USub: operator.neg,
        ast.Not: operator.not_,
    }

    # Allowed boolean operators
    ALLOWED_BOOL_OPS: Dict[type, str] = {
        ast.And: "and",
        ast.Or: "or",
    }

    # Allowed safe functions
    ALLOWED_FUNCTIONS: frozenset[str] = frozenset({
        "len",
        "str",
        "int",
        "float",
        "bool",
        "abs",
        "min",
        "max",
        "round",
        "sum",
        "any",
        "all",
        "sorted",
        "list",
        "tuple",
        "set",
        "dict",
        "range",
    })

    # Function implementations for safe execution
    SAFE_FUNCTIONS: Dict[str, Callable[..., Any]] = {
        "len": len,
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "abs": abs,
        "min": min,
        "max": max,
        "round": round,
        "sum": sum,
        "any": any,
        "all": all,
        "sorted": sorted,
        "list": list,
        "tuple": tuple,
        "set": set,
        "dict": dict,
        "range": range,
    }

    def __init__(
        self,
        max_length: int = MAX_EXPRESSION_LENGTH,
        max_depth: int = MAX_RECURSION_DEPTH,
        extra_functions: Optional[Dict[str, Callable[..., Any]]] = None,
    ):
        """Initialize the evaluator.

        Args:
            max_length: Maximum expression length in characters
            max_depth: Maximum recursion depth for nested expressions
            extra_functions: Additional allowed functions (must be safe!)
        """
        self.max_length = max_length
        self.max_depth = max_depth
        self._current_depth = 0

        # Extend safe functions if provided
        self.safe_functions = dict(self.SAFE_FUNCTIONS)
        if extra_functions:
            for name, func in extra_functions.items():
                if callable(func):
                    self.safe_functions[name] = func

    def evaluate(
        self,
        expression: str,
        variables: Optional[Dict[str, ExpressionValue]] = None,
    ) -> ExpressionValue:
        """Safely evaluate an expression.

        Args:
            expression: The expression string to evaluate
            variables: Variable bindings for the expression

        Returns:
            The result of the expression

        Raises:
            ExpressionSecurityError: If expression contains disallowed operations
            ExpressionEvaluationError: If evaluation fails
        """
        if not expression:
            return None

        # Length check
        if len(expression) > self.max_length:
            raise ExpressionSecurityError(
                f"Ausdruck zu lang: {len(expression)} > {self.max_length} Zeichen"
            )

        variables = variables or {}

        try:
            # Parse to AST
            tree = ast.parse(expression, mode="eval")

            # Reset depth counter
            self._current_depth = 0

            # Evaluate the AST
            return self._eval_node(tree.body, variables)

        except ExpressionSecurityError:
            raise
        except SyntaxError as e:
            raise ExpressionEvaluationError(
                f"Syntaxfehler im Ausdruck: {e}"
            )
        except Exception as e:
            logger.warning(
                "expression_evaluation_failed",
                expression=expression[:100],  # Truncate for logging
                **safe_error_log(e),
            )
            raise ExpressionEvaluationError(
                f"Auswertungsfehler: {e}"
            )

    def evaluate_condition(
        self,
        expression: str,
        variables: Optional[Dict[str, ExpressionValue]] = None,
    ) -> bool:
        """Evaluate an expression as a boolean condition.

        Args:
            expression: The condition expression
            variables: Variable bindings

        Returns:
            Boolean result of the condition
        """
        try:
            result = self.evaluate(expression, variables)
            return bool(result)
        except (ExpressionSecurityError, ExpressionEvaluationError):
            raise
        except Exception:
            return False

    def _eval_node(
        self,
        node: ast.AST,
        variables: Dict[str, ExpressionValue],
    ) -> ExpressionValue:
        """Recursively evaluate an AST node.

        Args:
            node: The AST node to evaluate
            variables: Variable bindings

        Returns:
            The evaluated value

        Raises:
            ExpressionSecurityError: If node type is not allowed
        """
        # Depth check
        self._current_depth += 1
        if self._current_depth > self.max_depth:
            raise ExpressionSecurityError(
                f"Maximale Verschachtelungstiefe erreicht: {self.max_depth}"
            )

        try:
            # Literals
            if isinstance(node, ast.Constant):
                return self._eval_constant(node)

            # Variables (names)
            if isinstance(node, ast.Name):
                return self._eval_name(node, variables)

            # Binary operations (+, -, *, /, etc.)
            if isinstance(node, ast.BinOp):
                return self._eval_binop(node, variables)

            # Unary operations (-, +, not)
            if isinstance(node, ast.UnaryOp):
                return self._eval_unaryop(node, variables)

            # Comparisons (==, !=, <, >, etc.)
            if isinstance(node, ast.Compare):
                return self._eval_compare(node, variables)

            # Boolean operations (and, or)
            if isinstance(node, ast.BoolOp):
                return self._eval_boolop(node, variables)

            # Conditional expression (x if condition else y)
            if isinstance(node, ast.IfExp):
                return self._eval_ifexp(node, variables)

            # Function calls (len, str, int, etc.)
            if isinstance(node, ast.Call):
                return self._eval_call(node, variables)

            # List literals
            if isinstance(node, ast.List):
                return self._eval_list(node, variables)

            # Dict literals
            if isinstance(node, ast.Dict):
                return self._eval_dict(node, variables)

            # Tuple literals
            if isinstance(node, ast.Tuple):
                return self._eval_tuple(node, variables)

            # Set literals
            if isinstance(node, ast.Set):
                return self._eval_set(node, variables)

            # Subscript (x[0], x["key"])
            if isinstance(node, ast.Subscript):
                return self._eval_subscript(node, variables)

            # Attribute access (x.y) - only for safe types
            if isinstance(node, ast.Attribute):
                return self._eval_attribute(node, variables)

            # Disallowed node type
            raise ExpressionSecurityError(
                f"Nicht erlaubter Ausdruck-Typ: {type(node).__name__}"
            )

        finally:
            self._current_depth -= 1

    def _eval_constant(self, node: ast.Constant) -> ExpressionValue:
        """Evaluate a constant literal."""
        value = node.value

        # Validate string length
        if isinstance(value, str) and len(value) > MAX_STRING_LENGTH:
            raise ExpressionSecurityError(
                f"String zu lang: {len(value)} > {MAX_STRING_LENGTH}"
            )

        return value

    def _eval_name(
        self,
        node: ast.Name,
        variables: Dict[str, ExpressionValue],
    ) -> ExpressionValue:
        """Evaluate a variable name."""
        name = node.id

        # Built-in constants
        if name == "True":
            return True
        if name == "False":
            return False
        if name == "None":
            return None

        # Variable lookup
        if name in variables:
            return variables[name]

        raise ExpressionEvaluationError(
            f"Unbekannte Variable: {name}"
        )

    def _eval_binop(
        self,
        node: ast.BinOp,
        variables: Dict[str, ExpressionValue],
    ) -> ExpressionValue:
        """Evaluate a binary operation."""
        op_type = type(node.op)

        if op_type not in self.ALLOWED_OPERATORS:
            raise ExpressionSecurityError(
                f"Nicht erlaubter Operator: {op_type.__name__}"
            )

        left = self._eval_node(node.left, variables)
        right = self._eval_node(node.right, variables)

        op_func = self.ALLOWED_OPERATORS[op_type]
        return op_func(left, right)

    def _eval_unaryop(
        self,
        node: ast.UnaryOp,
        variables: Dict[str, ExpressionValue],
    ) -> ExpressionValue:
        """Evaluate a unary operation."""
        op_type = type(node.op)

        if op_type not in self.ALLOWED_UNARY:
            raise ExpressionSecurityError(
                f"Nicht erlaubter unaerer Operator: {op_type.__name__}"
            )

        operand = self._eval_node(node.operand, variables)
        op_func = self.ALLOWED_UNARY[op_type]
        return op_func(operand)

    def _eval_compare(
        self,
        node: ast.Compare,
        variables: Dict[str, ExpressionValue],
    ) -> bool:
        """Evaluate a comparison."""
        left = self._eval_node(node.left, variables)

        result = True
        for op, comparator in zip(node.ops, node.comparators):
            op_type = type(op)

            if op_type not in self.ALLOWED_COMPARISONS:
                raise ExpressionSecurityError(
                    f"Nicht erlaubter Vergleichsoperator: {op_type.__name__}"
                )

            right = self._eval_node(comparator, variables)
            op_func = self.ALLOWED_COMPARISONS[op_type]

            if not op_func(left, right):
                result = False
                break

            left = right

        return result

    def _eval_boolop(
        self,
        node: ast.BoolOp,
        variables: Dict[str, ExpressionValue],
    ) -> ExpressionValue:
        """Evaluate a boolean operation (and/or)."""
        op_type = type(node.op)

        if op_type not in self.ALLOWED_BOOL_OPS:
            raise ExpressionSecurityError(
                f"Nicht erlaubter boolescher Operator: {op_type.__name__}"
            )

        if op_type == ast.And:
            # Short-circuit AND
            result: ExpressionValue = True
            for value_node in node.values:
                result = self._eval_node(value_node, variables)
                if not result:
                    return result
            return result
        else:
            # Short-circuit OR
            result = False
            for value_node in node.values:
                result = self._eval_node(value_node, variables)
                if result:
                    return result
            return result

    def _eval_ifexp(
        self,
        node: ast.IfExp,
        variables: Dict[str, ExpressionValue],
    ) -> ExpressionValue:
        """Evaluate a conditional expression."""
        condition = self._eval_node(node.test, variables)

        if condition:
            return self._eval_node(node.body, variables)
        else:
            return self._eval_node(node.orelse, variables)

    def _eval_call(
        self,
        node: ast.Call,
        variables: Dict[str, ExpressionValue],
    ) -> ExpressionValue:
        """Evaluate a function call."""
        if not isinstance(node.func, ast.Name):
            raise ExpressionSecurityError(
                "Nur einfache Funktionsaufrufe erlaubt (kein Methodenaufruf)"
            )

        func_name = node.func.id

        if func_name not in self.safe_functions:
            raise ExpressionSecurityError(
                f"Nicht erlaubte Funktion: {func_name}"
            )

        # Evaluate arguments
        args = [self._eval_node(arg, variables) for arg in node.args]

        # Evaluate keyword arguments
        kwargs = {}
        for keyword in node.keywords:
            if keyword.arg is None:
                raise ExpressionSecurityError(
                    "Keyword-Erweiterung (**kwargs) nicht erlaubt"
                )
            kwargs[keyword.arg] = self._eval_node(keyword.value, variables)

        # Call the safe function
        func = self.safe_functions[func_name]
        return func(*args, **kwargs)

    def _eval_list(
        self,
        node: ast.List,
        variables: Dict[str, ExpressionValue],
    ) -> list:
        """Evaluate a list literal."""
        return [self._eval_node(elem, variables) for elem in node.elts]

    def _eval_dict(
        self,
        node: ast.Dict,
        variables: Dict[str, ExpressionValue],
    ) -> dict:
        """Evaluate a dict literal."""
        result = {}
        for key, value in zip(node.keys, node.values):
            if key is None:
                raise ExpressionSecurityError(
                    "Dictionary-Erweiterung (**d) nicht erlaubt"
                )
            k = self._eval_node(key, variables)
            v = self._eval_node(value, variables)
            result[k] = v
        return result

    def _eval_tuple(
        self,
        node: ast.Tuple,
        variables: Dict[str, ExpressionValue],
    ) -> tuple:
        """Evaluate a tuple literal."""
        return tuple(self._eval_node(elem, variables) for elem in node.elts)

    def _eval_set(
        self,
        node: ast.Set,
        variables: Dict[str, ExpressionValue],
    ) -> set:
        """Evaluate a set literal."""
        return {self._eval_node(elem, variables) for elem in node.elts}

    def _eval_subscript(
        self,
        node: ast.Subscript,
        variables: Dict[str, ExpressionValue],
    ) -> ExpressionValue:
        """Evaluate a subscript operation (x[i])."""
        value = self._eval_node(node.value, variables)

        # Handle slice vs index
        if isinstance(node.slice, ast.Slice):
            lower = (
                self._eval_node(node.slice.lower, variables)
                if node.slice.lower else None
            )
            upper = (
                self._eval_node(node.slice.upper, variables)
                if node.slice.upper else None
            )
            step = (
                self._eval_node(node.slice.step, variables)
                if node.slice.step else None
            )
            return value[lower:upper:step]
        else:
            index = self._eval_node(node.slice, variables)
            return value[index]

    def _eval_attribute(
        self,
        node: ast.Attribute,
        variables: Dict[str, ExpressionValue],
    ) -> ExpressionValue:
        """Evaluate attribute access (limited to safe types)."""
        value = self._eval_node(node.value, variables)
        attr_name = node.attr

        # Only allow attribute access on safe types
        safe_types = (str, list, dict, set, tuple, Decimal)

        if not isinstance(value, safe_types):
            raise ExpressionSecurityError(
                f"Attributzugriff nicht erlaubt auf Typ: {type(value).__name__}"
            )

        # Disallow dunder attributes
        if attr_name.startswith("_"):
            raise ExpressionSecurityError(
                f"Zugriff auf private Attribute nicht erlaubt: {attr_name}"
            )

        return getattr(value, attr_name)


# Convenience function for simple evaluations
def safe_eval(
    expression: str,
    variables: Optional[Dict[str, ExpressionValue]] = None,
) -> ExpressionValue:
    """Safely evaluate an expression.

    This is a convenience function that creates a SafeExpressionEvaluator
    instance and evaluates the expression.

    Args:
        expression: The expression to evaluate
        variables: Variable bindings

    Returns:
        The result of the expression
    """
    evaluator = SafeExpressionEvaluator()
    return evaluator.evaluate(expression, variables)
