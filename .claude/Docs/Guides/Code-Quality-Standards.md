CODE QUALITY & STANDARDS GUIDE - TEIL 1
Complete Code Quality Strategy for Python Projects

📋 TABLE OF CONTENTS

Introduction
Python Style Guide (PEP 8)
Type Hints & mypy
Linting


🎯 INTRODUCTION
Why Code Quality Matters
┌─────────────────────────────────────────────────────────┐
│         CODE QUALITY BENEFITS                            │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  🐛 Fewer Bugs                                          │
│     - Catch errors before runtime                       │
│     - Type safety prevents common mistakes              │
│     - Consistent code reduces confusion                 │
│                                                         │
│  🚀 Faster Development                                  │
│     - Less time debugging                               │
│     - Easier to understand code                         │
│     - Better IDE support                                │
│     - Faster onboarding                                 │
│                                                         │
│  🔧 Easier Maintenance                                  │
│     - Consistent code style                             │
│     - Self-documenting code                             │
│     - Clear patterns                                    │
│     - Reduced technical debt                            │
│                                                         │
│  👥 Better Collaboration                                │
│     - Team follows same standards                       │
│     - Code reviews are faster                           │
│     - Less bikeshedding                                 │
│     - Knowledge sharing                                 │
│                                                         │
└─────────────────────────────────────────────────────────┘
Code Quality Stack
┌──────────────────────────────────────────────────────────────┐
│              CODE QUALITY TOOLS STACK                         │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Layer 1: Style Guide (Foundation)                           │
│  ┌────────────────────────────────────────────────┐         │
│  │ PEP 8 - Official Python Style Guide            │         │
│  └────────────────────────────────────────────────┘         │
│                         ↓                                    │
│  Layer 2: Type Checking                                      │
│  ┌────────────────────────────────────────────────┐         │
│  │ mypy - Static type checker                     │         │
│  │ Type hints - Runtime type information          │         │
│  └────────────────────────────────────────────────┘         │
│                         ↓                                    │
│  Layer 3: Linting (Code Analysis)                            │
│  ┌────────────────────────────────────────────────┐         │
│  │ Ruff - Fast all-in-one linter                  │         │
│  │ Flake8 - Style checker                         │         │
│  │ Pylint - Comprehensive analyzer                │         │
│  └────────────────────────────────────────────────┘         │
│                         ↓                                    │
│  Layer 4: Formatting (Auto-fix)                              │
│  ┌────────────────────────────────────────────────┐         │
│  │ Black - Code formatter                         │         │
│  │ isort - Import sorter                          │         │
│  └────────────────────────────────────────────────┘         │
│                         ↓                                    │
│  Layer 5: Automation                                         │
│  ┌────────────────────────────────────────────────┐         │
│  │ Pre-commit - Git hooks                         │         │
│  │ CI/CD - Automated checks                       │         │
│  └────────────────────────────────────────────────┘         │
│                                                              │
└──────────────────────────────────────────────────────────────┘

📖 PYTHON STYLE GUIDE (PEP 8)
1. Core PEP 8 Guidelines
python# style_guide_examples.py

"""
Python Style Guide Examples

Following PEP 8 - Python Enhancement Proposal 8
https://peps.python.org/pep-0008/
"""

# ============================================
# NAMING CONVENTIONS
# ============================================

# Classes: CapitalizedWords (PascalCase)
class UserRepository:
    """Repository for user data operations"""
    pass


class OCRProcessor:
    """OCR processing engine"""
    pass


# Functions and variables: lowercase_with_underscores (snake_case)
def process_document(file_path: str) -> dict:
    """Process a document and return results"""
    result_data = {}
    processing_status = "pending"
    return result_data


# Constants: UPPERCASE_WITH_UNDERSCORES
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
DEFAULT_TIMEOUT = 30
API_VERSION = "v1"


# Private methods/attributes: _leading_underscore
class FileProcessor:
    def __init__(self):
        self._cache = {}  # Private attribute
    
    def _validate_file(self, file_path: str) -> bool:
        """Private method for internal use"""
        return True


# Protected attributes: _single_leading_underscore
class BaseModel:
    def __init__(self):
        self._id = None  # Protected, can be accessed by subclasses


# Name mangling: __double_leading_underscore
class Encapsulated:
    def __init__(self):
        self.__private_data = []  # Name mangled to _Encapsulated__private_data


# Avoid: single trailing underscore for conflicts with keywords
class_ = "example"  # Avoids conflict with 'class' keyword
type_ = "string"    # Avoids conflict with 'type' builtin


# ============================================
# INDENTATION & LINE LENGTH
# ============================================

# Use 4 spaces per indentation level (NEVER tabs)
def example_function():
    if True:
        for item in items:
            process(item)


# Maximum line length: 79 characters (code), 72 (docstrings/comments)
# ✓ Good
def short_function_name(
    parameter_one: str,
    parameter_two: int,
    parameter_three: bool
) -> dict:
    """Short description fits in one line."""
    return {}


# Line continuation - use parentheses
# ✓ Good - Implicit line continuation
result = some_function(
    argument_one,
    argument_two,
    argument_three
)

# ✓ Good - Hanging indent
result = some_function(
    argument_one, argument_two,
    argument_three, argument_four
)


# ============================================
# IMPORTS
# ============================================

# Order: standard library, third-party, local
# ✓ Good
import os
import sys
from datetime import datetime
from typing import List, Dict, Optional

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException

from models.user import User
from services.ocr import OCRService
from core.cache import cache_manager


# ✗ Bad - Mixed order
from models.user import User
import os
from fastapi import FastAPI
import sys


# Absolute imports preferred over relative
# ✓ Good
from models.user import User
from services.ocr import OCRService

# ✗ Avoid (relative imports)
from ..models.user import User
from .ocr import OCRService


# One import per line for 'from' imports
# ✓ Good
from typing import List
from typing import Dict
from typing import Optional

# ✓ Also good - when importing multiple from same module
from typing import List, Dict, Optional

# ✗ Bad
import os, sys


# ============================================
# WHITESPACE
# ============================================

# Avoid extraneous whitespace
# ✓ Good
spam(ham[1], {eggs: 2})
if x == 4:
    print(x, y)
    x, y = y, x

# ✗ Bad
spam( ham[ 1 ], { eggs: 2 } )
if x == 4 :
    print(x , y)
    x , y = y , x


# Whitespace around operators
# ✓ Good
i = i + 1
submitted += 1
x = x * 2 - 1
hypot2 = x * x + y * y
c = (a + b) * (a - b)

# ✗ Bad
i=i+1
submitted +=1
x = x*2 - 1
hypot2 = x*x + y*y
c = (a+b) * (a-b)


# Function annotations
# ✓ Good
def complex_function(
    real: float,
    imag: float = 0.0
) -> complex:
    pass

# ✗ Bad
def complex_function(real:float,imag:float=0.0)->complex:
    pass


# ============================================
# BLANK LINES
# ============================================

# Two blank lines between top-level definitions
class FirstClass:
    pass


class SecondClass:
    pass


def top_level_function():
    pass


# One blank line between method definitions
class MyClass:
    def first_method(self):
        pass
    
    def second_method(self):
        pass


# Use blank lines sparingly inside functions
def example_with_sections():
    # Section 1: Setup
    data = load_data()
    
    # Section 2: Processing
    result = process_data(data)
    
    # Section 3: Return
    return result


# ============================================
# COMMENTS
# ============================================

# Inline comments - use sparingly
x = x + 1  # Compensate for border


# Block comments - explain complex logic
# This is a block comment explaining the following
# complex algorithm. Each line starts with #.
def complex_algorithm():
    pass


# ✗ Bad - Obvious comments
x = x + 1  # Increment x


# ============================================
# STRING QUOTES
# ============================================

# Single or double quotes - be consistent
# ✓ Good - pick one style and stick to it
message = "Hello World"
name = 'John Doe'

# Triple quotes for docstrings
def function():
    """
    This is a docstring.
    Use triple double quotes.
    """
    pass


# ============================================
# EXPRESSIONS & STATEMENTS
# ============================================

# Comparisons to singletons
# ✓ Good
if value is None:
    pass

if value is not None:
    pass

# ✗ Bad
if value == None:
    pass


# Boolean checks
# ✓ Good
if items:  # If list is not empty
    pass

if not items:  # If list is empty
    pass

# ✗ Bad
if len(items) > 0:
    pass

if len(items) == 0:
    pass


# Use 'is not' instead of 'not ... is'
# ✓ Good
if value is not None:
    pass

# ✗ Bad
if not value is None:
    pass


# ============================================
# FUNCTION ANNOTATIONS
# ============================================

# Use type hints for better code clarity
def process_file(
    file_path: str,
    encoding: str = 'utf-8',
    max_size: Optional[int] = None
) -> Dict[str, Any]:
    """
    Process file and return results.
    
    Args:
        file_path: Path to file
        encoding: File encoding
        max_size: Maximum file size in bytes
    
    Returns:
        Dictionary with processing results
    """
    return {}


# ============================================
# PROGRAMMING RECOMMENDATIONS
# ============================================

# String concatenation
# ✓ Good - Use f-strings (Python 3.6+)
name = "John"
age = 30
message = f"{name} is {age} years old"

# ✓ Good - For many strings
parts = ['Hello', 'World', '!']
message = ' '.join(parts)

# ✗ Bad - String concatenation in loops
message = ''
for part in parts:
    message += part  # Creates new string each iteration


# Check for prefix/suffix
# ✓ Good
if filename.startswith('temp'):
    pass

if filename.endswith('.txt'):
    pass

# ✗ Bad
if filename[:4] == 'temp':
    pass


# Object type comparison
# ✓ Good
if isinstance(obj, int):
    pass

# ✗ Bad
if type(obj) is int:
    pass


# Use context managers
# ✓ Good
with open('file.txt') as f:
    data = f.read()

# ✗ Bad
f = open('file.txt')
data = f.read()
f.close()


# Return consistency
# ✓ Good
def get_value(key: str) -> Optional[str]:
    if key in cache:
        return cache[key]
    return None  # Explicit None

# ✗ Bad
def get_value(key: str) -> Optional[str]:
    if key in cache:
        return cache[key]
    # Implicit None


# Use 'with' for resource management
# ✓ Good
with lock:
    # Critical section
    shared_resource.modify()

# ✗ Bad
lock.acquire()
try:
    shared_resource.modify()
finally:
    lock.release()


# ============================================
# EXCEPTIONS
# ============================================

# Be specific with exception handling
# ✓ Good
try:
    value = int(user_input)
except ValueError as e:
    logger.error(f"Invalid integer: {e}")
    raise

# ✗ Bad - Too broad
try:
    value = int(user_input)
except Exception:
    pass


# Use finally for cleanup
try:
    resource = acquire_resource()
    process(resource)
except ProcessingError:
    logger.error("Processing failed")
    raise
finally:
    release_resource(resource)


# Chain exceptions with 'from'
try:
    do_something()
except ValueError as e:
    raise CustomError("Something went wrong") from e
2. Project-Specific Style Guide
python# project_style_guide.py

"""
Project-Specific Style Guide

Extends PEP 8 with project conventions
"""

# ============================================
# PROJECT NAMING CONVENTIONS
# ============================================

# File names: lowercase_with_underscores
# ✓ Good
# user_repository.py
# ocr_service.py
# cache_manager.py

# ✗ Bad
# UserRepository.py
# OCRService.py
# cacheManager.py


# Package names: lowercase, no underscores if possible
# ✓ Good
# models/
# services/
# api/

# ✗ Bad
# Models/
# api_endpoints/


# Module names should be short and descriptive
# ✓ Good
# auth.py
# cache.py
# utils.py

# ✗ Bad
# authentication_and_authorization.py


# ============================================
# API ENDPOINT NAMING
# ============================================

# RESTful naming conventions
# ✓ Good
@router.get("/users")  # List users
@router.get("/users/{user_id}")  # Get user
@router.post("/users")  # Create user
@router.put("/users/{user_id}")  # Update user
@router.delete("/users/{user_id}")  # Delete user

# ✗ Bad
@router.get("/get_users")
@router.post("/create_user")


# ============================================
# DATABASE MODELS
# ============================================

# Table names: plural, lowercase
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True)


# Foreign key naming
class Document(Base):
    __tablename__ = "documents"
    
    # Format: {referenced_table}_id
    user_id = Column(Integer, ForeignKey("users.id"))


# ============================================
# ERROR HANDLING
# ============================================

# Custom exceptions - end with 'Error'
class ValidationError(Exception):
    """Raised when validation fails"""
    pass


class OCRProcessingError(Exception):
    """Raised when OCR processing fails"""
    pass


# ============================================
# LOGGING
# ============================================

# Logger naming - use module name
import logging

logger = logging.getLogger(__name__)

# Log levels usage:
logger.debug("Detailed information for debugging")
logger.info("General information about application flow")
logger.warning("Warning about potential issues")
logger.error("Error that needs attention")
logger.critical("Critical error, application may crash")


# ============================================
# CONFIGURATION
# ============================================

# Environment variables: UPPERCASE_WITH_UNDERSCORES
# .env file:
# DATABASE_URL=postgresql://...
# REDIS_HOST=localhost
# API_SECRET_KEY=...


# Settings class attributes
class Settings:
    DATABASE_URL: str
    REDIS_HOST: str
    API_SECRET_KEY: str


# ============================================
# TYPE ALIASES
# ============================================

from typing import Dict, List, Optional

# Define type aliases for complex types
UserID = int
DocumentID = int
Metadata = Dict[str, any]
FileList = List[str]


def process_users(user_ids: List[UserID]) -> Dict[UserID, Metadata]:
    """More readable with type aliases"""
    pass


# ============================================
# DOCSTRING FORMAT
# ============================================

def example_function(
    param1: str,
    param2: int,
    param3: Optional[bool] = None
) -> Dict[str, Any]:
    """
    One-line summary.
    
    Detailed description if needed. Can span multiple
    lines and paragraphs.
    
    Args:
        param1: Description of param1
        param2: Description of param2
        param3: Description of param3, defaults to None
    
    Returns:
        Dictionary containing results with keys:
        - 'status': Processing status
        - 'data': Result data
    
    Raises:
        ValueError: If param1 is empty
        ProcessingError: If processing fails
    
    Example:
        >>> result = example_function("test", 42)
        >>> print(result['status'])
        'success'
    """
    pass

🔢 TYPE HINTS & MYPY
1. Complete Type Hints Guide
python# type_hints_guide.py

"""
Complete Type Hints Guide

Using Python's typing module for static type checking
"""

from typing import (
    Any, Dict, List, Set, Tuple, Optional, Union,
    Callable, Type, TypeVar, Generic, Protocol,
    Literal, Final, ClassVar, cast, overload
)
from collections.abc import Iterable, Sequence, Mapping
from pathlib import Path
from datetime import datetime


# ============================================
# BASIC TYPES
# ============================================

# Built-in types
name: str = "John"
age: int = 30
price: float = 19.99
is_active: bool = True


# Collections
items: list = [1, 2, 3]  # Old style (Python 3.9+)
items: List[int] = [1, 2, 3]  # Explicit typing

# Python 3.9+ - use built-in generics
items: list[int] = [1, 2, 3]
mapping: dict[str, int] = {"a": 1, "b": 2}
unique: set[str] = {"a", "b", "c"}
coords: tuple[int, int] = (10, 20)


# ============================================
# OPTIONAL & UNION
# ============================================

# Optional - value or None
def get_user(user_id: int) -> Optional[User]:
    """Returns User or None if not found"""
    if user_id in cache:
        return cache[user_id]
    return None


# Union - one of multiple types
def process_input(data: Union[str, int, List[str]]) -> str:
    """Handle multiple input types"""
    if isinstance(data, str):
        return data
    elif isinstance(data, int):
        return str(data)
    else:
        return ", ".join(data)


# Python 3.10+ - use | operator
def process_input(data: str | int | list[str]) -> str:
    """Cleaner syntax"""
    pass


# ============================================
# FUNCTIONS
# ============================================

# Function with type hints
def greet(name: str, age: int) -> str:
    """Returns greeting message"""
    return f"Hello {name}, you are {age} years old"


# Function with optional parameters
def create_user(
    email: str,
    username: str,
    age: Optional[int] = None,
    is_admin: bool = False
) -> User:
    """Create new user"""
    pass


# Function with *args and **kwargs
def process_data(
    *args: str,
    **kwargs: int
) -> Dict[str, int]:
    """Process variable arguments"""
    pass


# Callable type - functions as parameters
def apply_operation(
    data: List[int],
    operation: Callable[[int], int]
) -> List[int]:
    """Apply operation to each element"""
    return [operation(x) for x in data]


# Example usage:
def double(x: int) -> int:
    return x * 2

result = apply_operation([1, 2, 3], double)


# ============================================
# CLASSES
# ============================================

class User:
    """User model with type hints"""
    
    # Class variable
    default_role: ClassVar[str] = "user"
    
    def __init__(
        self,
        email: str,
        username: str,
        age: Optional[int] = None
    ) -> None:
        self.email: str = email
        self.username: str = username
        self.age: Optional[int] = age
        self.created_at: datetime = datetime.now()
    
    def get_display_name(self) -> str:
        """Return display name"""
        return self.username
    
    def is_adult(self) -> bool:
        """Check if user is adult"""
        if self.age is None:
            return False
        return self.age >= 18


# ============================================
# GENERICS
# ============================================

T = TypeVar('T')


# Generic function
def first_element(items: List[T]) -> Optional[T]:
    """Return first element or None"""
    return items[0] if items else None


# Generic class
class Stack(Generic[T]):
    """Generic stack implementation"""
    
    def __init__(self) -> None:
        self._items: List[T] = []
    
    def push(self, item: T) -> None:
        """Push item onto stack"""
        self._items.append(item)
    
    def pop(self) -> Optional[T]:
        """Pop item from stack"""
        return self._items.pop() if self._items else None


# Usage
int_stack: Stack[int] = Stack()
int_stack.push(1)
int_stack.push(2)

str_stack: Stack[str] = Stack()
str_stack.push("hello")


# ============================================
# PROTOCOLS (Structural Typing)
# ============================================

class Drawable(Protocol):
    """Protocol for drawable objects"""
    
    def draw(self) -> None:
        """Draw the object"""
        ...


# Any class with draw() method satisfies this protocol
class Circle:
    def draw(self) -> None:
        print("Drawing circle")


class Square:
    def draw(self) -> None:
        print("Drawing square")


def render(obj: Drawable) -> None:
    """Render any drawable object"""
    obj.draw()


# Both work!
render(Circle())
render(Square())


# ============================================
# LITERAL
# ============================================

from typing import Literal

# Literal types - specify exact values
Status = Literal["pending", "processing", "completed", "failed"]


def set_status(status: Status) -> None:
    """Set status to specific values only"""
    pass


# Type checker ensures only valid values
set_status("pending")  # ✓ OK
set_status("invalid")  # ✗ Type error


# ============================================
# FINAL
# ============================================

# Final - cannot be overridden
class Base:
    MAX_SIZE: Final[int] = 100
    
    @final
    def critical_method(self) -> None:
        """Cannot be overridden in subclasses"""
        pass


# ============================================
# TYPE ALIASES
# ============================================

# Simple alias
UserID = int
DocumentID = int


# Complex alias
JSONDict = Dict[str, Any]
Headers = Dict[str, str]
QueryParams = Dict[str, Union[str, int, bool]]


def make_request(
    url: str,
    headers: Headers,
    params: QueryParams
) -> JSONDict:
    """Make HTTP request"""
    pass


# ============================================
# OVERLOAD
# ============================================

@overload
def process_value(value: int) -> int:
    ...


@overload
def process_value(value: str) -> str:
    ...


def process_value(value: Union[int, str]) -> Union[int, str]:
    """Process value based on type"""
    if isinstance(value, int):
        return value * 2
    return value.upper()


# ============================================
# CAST
# ============================================

# Use cast() when you know better than type checker
from typing import cast

def get_config() -> Any:
    """Returns config dict"""
    return {"key": "value"}


# Tell type checker this is a dict
config: Dict[str, str] = cast(Dict[str, str], get_config())


# ============================================
# TYPE CHECKING ONLY IMPORTS
# ============================================

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Imports only used for type hints
    # Not imported at runtime
    from models.user import User
    from models.document import Document


def process_user(user: 'User') -> 'Document':
    """Use string annotations to avoid runtime import"""
    pass


# ============================================
# ADVANCED PATTERNS
# ============================================

# Factory function with type hints
def create_processor(
    processor_type: Type[T]
) -> T:
    """Factory function"""
    return processor_type()


# Context manager
from contextlib import contextmanager
from typing import Generator


@contextmanager
def database_session() -> Generator[Session, None, None]:
    """Database session context manager"""
    session = Session()
    try:
        yield session
        session.commit()
    except:
        session.rollback()
        raise
    finally:
        session.close()


# Async functions
async def fetch_data(url: str) -> Dict[str, Any]:
    """Async function with type hints"""
    pass


# Async generator
async def stream_data() -> AsyncGenerator[str, None]:
    """Async generator"""
    for i in range(10):
        yield str(i)
2. mypy Configuration
ini# mypy.ini

# ============================================
# MYPY CONFIGURATION
# ============================================
#
# Static type checker configuration
#
# ============================================

[mypy]
# Python version
python_version = 3.11

# Output
show_error_codes = true
show_column_numbers = true
show_error_context = true
pretty = true
color_output = true

# Strictness
warn_return_any = true
warn_unused_configs = true
warn_redundant_casts = true
warn_unused_ignores = true
warn_no_return = true
warn_unreachable = true

# Untyped definitions
disallow_untyped_defs = true
disallow_incomplete_defs = true
disallow_untyped_calls = true
disallow_untyped_decorators = false  # Too strict for decorators

# None and Optional
no_implicit_optional = true
strict_optional = true

# Type checking
check_untyped_defs = true
disallow_any_generics = true
disallow_subclassing_any = true

# Imports
ignore_missing_imports = false
follow_imports = normal

# Error output
show_traceback = true

# Warnings
warn_unused_ignores = true
warn_return_any = true

# Strictness per module
[mypy-tests.*]
disallow_untyped_defs = false

[mypy-scripts.*]
disallow_untyped_defs = false

# Third-party libraries without stubs
[mypy-celery.*]
ignore_missing_imports = true

[mypy-redis.*]
ignore_missing_imports = true

[mypy-sqlalchemy.*]
ignore_missing_imports = true
toml# pyproject.toml - Alternative mypy config

[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
show_error_codes = true

# Per-module options
[[tool.mypy.overrides]]
module = "tests.*"
disallow_untyped_defs = false

[[tool.mypy.overrides]]
module = [
    "celery.*",
    "redis.*",
]
ignore_missing_imports = true
3. Running mypy
bash# scripts/run_mypy.sh

#!/bin/bash
# ============================================
# RUN MYPY TYPE CHECKING
# ============================================

echo "Running mypy type checker..."
echo "=" * 50

# Basic check
mypy .

# Check specific directory
mypy backend/

# Check specific files
mypy models/ services/ api/

# Show detailed report
mypy --html-report mypy_report .

# Check only changed files (with git)
mypy $(git diff --name-only --diff-filter=ACMR | grep '\.py$')

# Strict mode
mypy --strict .

# Generate coverage report
mypy --html-report ./mypy_report --cobertura-xml-report ./mypy_report .

# Different output formats
mypy --junit-xml mypy_junit.xml .
mypy --txt-report mypy_report .

echo ""
echo "Type checking complete!"

🔍 LINTING
1. Ruff Configuration (Recommended)
toml# pyproject.toml

[tool.ruff]
# Target Python 3.11
target-version = "py311"

# Line length
line-length = 100

# Directories to exclude
exclude = [
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "__pycache__",
    "build",
    "dist",
]

# Enable auto-fixing
fix = true
show-fixes = true

[tool.ruff.lint]
# Enable rule sets
select = [
    "E",    # pycodestyle errors
    "W",    # pycodestyle warnings
    "F",    # pyflakes
    "I",    # isort
    "B",    # flake8-bugbear
    "C4",   # flake8-comprehensions
    "UP",   # pyupgrade
    "ARG",  # flake8-unused-arguments
    "SIM",  # flake8-simplify
    "TCH",  # flake8-type-checking
    "PTH",  # flake8-use-pathlib
    "ERA",  # eradicate (commented code)
    "PL",   # pylint
    "RUF",  # Ruff-specific rules
]

# Ignore specific rules
ignore = [
    "E501",  # Line too long (handled by formatter)
    "B008",  # Do not perform function calls in argument defaults
    "PLR0913",  # Too many arguments
    "PLR2004",  # Magic value used in comparison
]

# Allow autofix for all enabled rules
fixable = ["ALL"]
unfixable = []

# Ignore in specific files
[tool.ruff.lint.per-file-ignores]
"__init__.py" = ["F401"]  # Unused imports in __init__
"tests/**/*.py" = [
    "S101",  # Use of assert
    "ARG",   # Unused arguments in tests
    "PLR2004",  # Magic values in tests
]

[tool.ruff.lint.mccabe]
# Maximum cyclomatic complexity
max-complexity = 10

[tool.ruff.lint.isort]
# isort configuration
known-first-party = ["models", "services", "api", "core"]
section-order = [
    "future",
    "standard-library",
    "third-party",
    "first-party",
    "local-folder"
]

[tool.ruff.lint.pydocstyle]
# Docstring convention
convention = "google"
2. Flake8 Configuration
ini# .flake8

[flake8]
# Maximum line length
max-line-length = 100

# Maximum complexity
max-complexity = 10

# Exclude directories
exclude =
    .git,
    __pycache__,
    .venv,
    venv,
    build,
    dist,
    *.egg-info

# Ignore specific errors
ignore =
    E203,  # Whitespace before ':'
    E266,  # Too many leading '#' for block comment
    E501,  # Line too long (handled by black)
    W503,  # Line break before binary operator

# Per-file ignores
per-file-ignores =
    __init__.py:F401,F403
    tests/*.py:S101

# Enable flake8 plugins
enable-extensions =
    G  # flake8-logging-format

# docstring checking
docstring-convention = google

# Import order
import-order-style = google
application-import-names = models,services,api,core
3. Pylint Configuration
ini# .pylintrc

[MASTER]
# Python version
py-version=3.11

# Pickle collected data
persistent=yes

# Directories to ignore
ignore=.git,__pycache__,.venv,venv,build,dist

# Parallel jobs
jobs=0

[MESSAGES CONTROL]
# Disable specific warnings
disable=
    C0111,  # missing-docstring
    C0103,  # invalid-name
    R0903,  # too-few-public-methods
    R0913,  # too-many-arguments
    W0212,  # protected-access
    W0511,  # fixme

[FORMAT]
# Maximum line length
max-line-length=100

# Maximum lines in module
max-module-lines=1000

# String quote preference
string-quote=double

# Indent string
indent-string='    '

[BASIC]
# Good variable names
good-names=i,j,k,ex,_,id,db

# Naming conventions
variable-rgx=[a-z_][a-z0-9_]{2,30}$
const-rgx=(([A-Z_][A-Z0-9_]*)|(__.*__))$
attr-rgx=[a-z_][a-z0-9_]{2,30}$
argument-rgx=[a-z_][a-z0-9_]{2,30}$
class-attribute-rgx=([A-Za-z_][A-Za-z0-9_]{2,30}|(__.*__))$
method-rgx=[a-z_][a-z0-9_]{2,30}$
class-rgx=[A-Z_][a-zA-Z0-9]+$
function-rgx=[a-z_][a-z0-9_]{2,30}$
module-rgx=(([a-z_][a-z0-9_]*)|([A-Z][a-zA-Z0-9]+))$

[DESIGN]
# Maximum arguments
max-args=7

# Maximum locals
max-locals=15

# Maximum returns
max-returns=6

# Maximum branches
max-branches=12

# Maximum statements
max-statements=50

# Maximum attributes
max-attributes=10

# Minimum public methods
min-public-methods=1

# Maximum public methods
max-public-methods=20

[IMPORTS]
# Deprecated modules
deprecated-modules=optparse,imp

[EXCEPTIONS]
# Exceptions that trigger warnings
overgeneral-exceptions=builtins.Exception
4. Running Linters
python# scripts/run_linters.py

"""
Run all linters

Executes linting checks and reports results
"""

import subprocess
import sys
from pathlib import Path
from typing import List, Tuple


class LinterRunner:
    """Run multiple linters and aggregate results"""
    
    def __init__(self, root_dir: Path = None):
        """Initialize linter runner"""
        self.root_dir = root_dir or Path.cwd()
        self.results: List[Tuple[str, int, str]] = []
    
    def run_ruff(self) -> int:
        """Run Ruff linter"""
        print("=" * 60)
        print("Running Ruff...")
        print("=" * 60)
        
        result = subprocess.run(
            ["ruff", "check", "."],
            capture_output=True,
            text=True
        )
        
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        
        self.results.append(("Ruff", result.returncode, result.stdout))
        
        return result.returncode
    
    def run_flake8(self) -> int:
        """Run Flake8"""
        print("\n" + "=" * 60)
        print("Running Flake8...")
        print("=" * 60)
        
        result = subprocess.run(
            ["flake8", "."],
            capture_output=True,
            text=True
        )
        
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        
        self.results.append(("Flake8", result.returncode, result.stdout))
        
        return result.returncode
    
    def run_pylint(self) -> int:
        """Run Pylint"""
        print("\n" + "=" * 60)
        print("Running Pylint...")
        print("=" * 60)
        
        result = subprocess.run(
            ["pylint", "models", "services", "api"],
            capture_output=True,
            text=True
        )
        
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        
        self.results.append(("Pylint", result.returncode, result.stdout))
        
        return result.returncode
    
    def run_mypy(self) -> int:
        """Run mypy"""
        print("\n" + "=" * 60)
        print("Running mypy...")
        print("=" * 60)
        
        result = subprocess.run(
            ["mypy", "."],
            capture_output=True,
            text=True
        )
        
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        
        self.results.append(("mypy", result.returncode, result.stdout))
        
        return result.returncode
    
    def run_all(self) -> int:
        """
        Run all linters
        
        Returns:
            0 if all passed, 1 if any failed
        """
        exit_codes = [
            self.run_ruff(),
            self.run_flake8(),
            self.run_pylint(),
            self.run_mypy()
        ]
        
        # Summary
        print("\n" + "=" * 60)
        print("LINTING SUMMARY")
        print("=" * 60)
        
        for name, code, _ in self.results:
            status = "✓ PASSED" if code == 0 else "✗ FAILED"
            print(f"{name:20} {status}")
        
        total_errors = sum(1 for _, code, _ in self.results if code != 0)
        
        print("=" * 60)
        print(f"Total: {len(self.results)} linters, {total_errors} failed")
        
        return 1 if any(exit_codes) else 0


if __name__ == "__main__":
    runner = LinterRunner()
    exit_code = runner.run_all()
    sys.exit(exit_code)
bash# scripts/lint.sh

#!/bin/bash
# ============================================
# COMPREHENSIVE LINTING SCRIPT
# ============================================

set -e  # Exit on error

echo "Starting linting process..."
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

FAILED=0

# ============================================
# RUFF
# ============================================

echo "Running Ruff..."
if ruff check .; then
    echo -e "${GREEN}✓ Ruff passed${NC}"
else
    echo -e "${RED}✗ Ruff failed${NC}"
    FAILED=1
fi
echo ""

# ============================================
# FLAKE8
# ============================================

echo "Running Flake8..."
if flake8 .; then
    echo -e "${GREEN}✓ Flake8 passed${NC}"
else
    echo -e "${RED}✗ Flake8 failed${NC}"
    FAILED=1
fi
echo ""

# ============================================
# PYLINT
# ============================================

echo "Running Pylint..."
if pylint models services api; then
    echo -e "${GREEN}✓ Pylint passed${NC}"
else
    echo -e "${RED}✗ Pylint failed${NC}"
    FAILED=1
fi
echo ""

# ============================================
# MYPY
# ============================================

echo "Running mypy..."
if mypy .; then
    echo -e "${GREEN}✓ mypy passed${NC}"
else
    echo -e "${RED}✗ mypy failed${NC}"
    FAILED=1
fi
echo ""

# ============================================
# SUMMARY
# ============================================

echo "=========================================="
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All linting checks passed!${NC}"
    exit 0
else
    echo -e "${RED}✗ Some linting checks failed${NC}"
    exit 1
fi

CODE QUALITY & STANDARDS GUIDE - TEIL 2
Formatting, Pre-commit Hooks & Automation

📋 TABLE OF CONTENTS (TEIL 2)

Formatting (Black & isort)
Pre-commit Hooks
Code Review Guidelines


🎨 FORMATTING (BLACK & ISORT)
1. Black Configuration
toml# pyproject.toml

[tool.black]
# Line length
line-length = 100

# Target Python versions
target-version = ['py311']

# Include
include = '\.pyi?$'

# Exclude
extend-exclude = '''
/(
    # directories
    \.eggs
  | \.git
  | \.hg
  | \.mypy_cache
  | \.tox
  | \.venv
  | venv
  | _build
  | buck-out
  | build
  | dist
  | migrations
)/
'''

# Enable preview features
preview = false

# String normalization
skip-string-normalization = false

# Magic trailing comma
skip-magic-trailing-comma = false
2. Black Examples
python# before_black.py - Before Black formatting

"""
Code before Black formatting
"""

# ============================================
# IMPORTS - Will be reformatted
# ============================================

from typing import List,Dict,Optional
import os,sys
from datetime import datetime,timedelta


# ============================================
# LONG LINES - Will be wrapped
# ============================================

def very_long_function_name(first_parameter, second_parameter, third_parameter, fourth_parameter, fifth_parameter):
    """Function with too many parameters on one line"""
    pass


# String concatenation - will be reformatted
message = "This is a very long string that should probably be " + "split across multiple lines " + "for better readability"


# ============================================
# INCONSISTENT SPACING
# ============================================

result=some_function(param1,param2,param3)
if condition1 and condition2 or condition3:
    do_something( )

dictionary = { 'key1':'value1','key2':'value2','key3':'value3' }


# ============================================
# STRING QUOTES - Will be normalized
# ============================================

single_quotes = 'single'
double_quotes = "double"
mixed = 'single and "double"'
python# after_black.py - After Black formatting

"""
Code after Black formatting
"""

# ============================================
# IMPORTS - Cleaned up
# ============================================

import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional


# ============================================
# LONG LINES - Wrapped nicely
# ============================================

def very_long_function_name(
    first_parameter,
    second_parameter,
    third_parameter,
    fourth_parameter,
    fifth_parameter,
):
    """Function with parameters properly wrapped"""
    pass


# String concatenation - reformatted
message = (
    "This is a very long string that should probably be "
    "split across multiple lines "
    "for better readability"
)


# ============================================
# CONSISTENT SPACING
# ============================================

result = some_function(param1, param2, param3)
if condition1 and condition2 or condition3:
    do_something()

dictionary = {"key1": "value1", "key2": "value2", "key3": "value3"}


# ============================================
# STRING QUOTES - Normalized to double quotes
# ============================================

single_quotes = "single"
double_quotes = "double"
mixed = 'single and "double"'  # Mixed quotes preserved when needed
3. isort Configuration
toml# pyproject.toml

[tool.isort]
# Profile - use black-compatible settings
profile = "black"

# Line length (match black)
line_length = 100

# Multi-line output mode
multi_line_output = 3

# Trailing comma
include_trailing_comma = true

# Force grid wrap
force_grid_wrap = 0

# Use parentheses
use_parentheses = true

# Ensure newline before comments
ensure_newline_before_comments = true

# Split on trailing comma
split_on_trailing_comma = true

# Known first-party packages
known_first_party = ["models", "services", "api", "core", "utils"]

# Known third-party packages
known_third_party = [
    "fastapi",
    "sqlalchemy",
    "pydantic",
    "redis",
    "celery",
]

# Section order
sections = [
    "FUTURE",
    "STDLIB",
    "THIRDPARTY",
    "FIRSTPARTY",
    "LOCALFOLDER",
]

# Import headings
import_heading_future = "Future imports"
import_heading_stdlib = "Standard library"
import_heading_thirdparty = "Third-party"
import_heading_firstparty = "First-party"
import_heading_localfolder = "Local"

# Skip files
skip_glob = [
    "*.egg-info/*",
    "build/*",
    "dist/*",
    ".venv/*",
    "venv/*",
]

# Skip these imports
skip = ["__init__.py"]

# Force single line
force_single_line = false

# Force alphabetical sorting within sections
force_alphabetical_sort_within_sections = false

# Case sensitive
case_sensitive = false

# Remove redundant aliases
remove_redundant_aliases = true

# Honor noqa comments
honor_noqa = true
4. isort Examples
python# before_isort.py - Before isort

"""
Imports before isort formatting
"""

# Mixed order imports
from models.user import User
import os
from fastapi import FastAPI, HTTPException
import sys
from typing import List, Optional
from datetime import datetime
from services.ocr import OCRService
import json
from sqlalchemy.orm import Session
from core.cache import cache_manager
import logging


def example():
    pass
python# after_isort.py - After isort

"""
Imports after isort formatting
"""

# Future imports

# Standard library
import json
import logging
import os
import sys
from datetime import datetime
from typing import List, Optional

# Third-party
from fastapi import FastAPI, HTTPException
from sqlalchemy.orm import Session

# First-party
from core.cache import cache_manager
from models.user import User
from services.ocr import OCRService


def example():
    pass
5. Running Formatters
bash# scripts/format.sh

#!/bin/bash
# ============================================
# AUTO-FORMAT CODE
# ============================================

set -e

echo "Formatting code..."
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# ============================================
# ISORT - Sort imports
# ============================================

echo "Running isort..."
isort . --diff --check-only

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Imports already sorted${NC}"
else
    echo -e "${YELLOW}→ Sorting imports...${NC}"
    isort .
    echo -e "${GREEN}✓ Imports sorted${NC}"
fi
echo ""

# ============================================
# BLACK - Format code
# ============================================

echo "Running black..."
black . --check

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Code already formatted${NC}"
else
    echo -e "${YELLOW}→ Formatting code...${NC}"
    black .
    echo -e "${GREEN}✓ Code formatted${NC}"
fi
echo ""

echo -e "${GREEN}✓ All formatting complete!${NC}"
python# scripts/format_code.py

"""
Code Formatting Script

Runs Black and isort on the codebase
"""

import subprocess
import sys
from pathlib import Path
from typing import List, Tuple


class CodeFormatter:
    """Format code using Black and isort"""
    
    def __init__(self, root_dir: Path = None):
        """Initialize formatter"""
        self.root_dir = root_dir or Path.cwd()
    
    def run_isort(self, check_only: bool = False) -> bool:
        """
        Run isort
        
        Args:
            check_only: Only check, don't modify
        
        Returns:
            True if formatting needed
        """
        print("=" * 60)
        print("Running isort...")
        print("=" * 60)
        
        cmd = ["isort", "."]
        if check_only:
            cmd.extend(["--check-only", "--diff"])
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )
        
        if result.stdout:
            print(result.stdout)
        
        if result.returncode != 0:
            if check_only:
                print("✗ Imports need sorting")
                return True
            else:
                print("✗ isort failed")
                return False
        else:
            print("✓ Imports sorted correctly")
            return False
    
    def run_black(self, check_only: bool = False) -> bool:
        """
        Run Black
        
        Args:
            check_only: Only check, don't modify
        
        Returns:
            True if formatting needed
        """
        print("\n" + "=" * 60)
        print("Running Black...")
        print("=" * 60)
        
        cmd = ["black", "."]
        if check_only:
            cmd.append("--check")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )
        
        if result.stdout:
            print(result.stdout)
        
        if result.returncode != 0:
            if check_only:
                print("✗ Code needs formatting")
                return True
            else:
                print("✗ Black failed")
                return False
        else:
            print("✓ Code formatted correctly")
            return False
    
    def format_all(self, check_only: bool = False) -> int:
        """
        Run all formatters
        
        Args:
            check_only: Only check, don't modify
        
        Returns:
            0 if all good, 1 if formatting needed/failed
        """
        needs_formatting = []
        
        # Run isort
        if self.run_isort(check_only):
            needs_formatting.append("isort")
        
        # Run Black
        if self.run_black(check_only):
            needs_formatting.append("black")
        
        # Summary
        print("\n" + "=" * 60)
        print("FORMATTING SUMMARY")
        print("=" * 60)
        
        if needs_formatting:
            if check_only:
                print(f"✗ Formatting needed: {', '.join(needs_formatting)}")
                print("\nRun 'python scripts/format_code.py' to fix")
            else:
                print("✗ Some formatters failed")
            return 1
        else:
            print("✓ All code properly formatted!")
            return 0


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Format code")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only check, don't modify"
    )
    
    args = parser.parse_args()
    
    formatter = CodeFormatter()
    exit_code = formatter.format_all(check_only=args.check)
    sys.exit(exit_code)
6. Makefile Integration
makefile# Makefile

# ============================================
# CODE QUALITY COMMANDS
# ============================================

.PHONY: format format-check lint type-check quality-check

# Format code
format:
	@echo "Formatting code..."
	isort .
	black .
	@echo "✓ Code formatted"

# Check formatting without changes
format-check:
	@echo "Checking code formatting..."
	isort . --check-only --diff
	black . --check
	@echo "✓ Format check complete"

# Run linters
lint:
	@echo "Running linters..."
	ruff check .
	flake8 .
	pylint models services api
	@echo "✓ Linting complete"

# Run type checker
type-check:
	@echo "Running type checker..."
	mypy .
	@echo "✓ Type checking complete"

# Run all quality checks
quality-check: format-check lint type-check
	@echo "✓ All quality checks passed!"

# Fix auto-fixable issues
fix:
	@echo "Auto-fixing issues..."
	ruff check . --fix
	isort .
	black .
	@echo "✓ Auto-fixes applied"

# Format specific file
format-file:
	@echo "Formatting $(FILE)..."
	isort $(FILE)
	black $(FILE)
	@echo "✓ File formatted"

🪝 PRE-COMMIT HOOKS
1. Pre-commit Configuration
yaml# .pre-commit-config.yaml

# ============================================
# PRE-COMMIT HOOKS CONFIGURATION
# ============================================
#
# Automatically format and check code before commits
#
# Installation:
#   pip install pre-commit
#   pre-commit install
#
# ============================================

# Minimum pre-commit version
minimum_pre_commit_version: '2.20.0'

# Don't fail on missing config
fail_fast: false

# Repositories
repos:
  # ============================================
  # PRE-COMMIT HOOKS (Built-in)
  # ============================================
  
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      # Check for files that would conflict in case-insensitive filesystems
      - id: check-case-conflict
      
      # Check for merge conflicts
      - id: check-merge-conflict
      
      # Check YAML files
      - id: check-yaml
        args: ['--unsafe']  # Allow custom tags
      
      # Check TOML files
      - id: check-toml
      
      # Check JSON files
      - id: check-json
      
      # Check for added large files
      - id: check-added-large-files
        args: ['--maxkb=1000']  # 1MB limit
      
      # Check for private keys
      - id: detect-private-key
      
      # Check Python AST
      - id: check-ast
      
      # Check for debugger imports
      - id: debug-statements
      
      # Check docstring is first
      - id: check-docstring-first
      
      # Fix end of files
      - id: end-of-file-fixer
      
      # Fix trailing whitespace
      - id: trailing-whitespace
        args: [--markdown-linebreak-ext=md]
      
      # Mixed line endings
      - id: mixed-line-ending
        args: ['--fix=lf']
      
      # Check for executable text files
      - id: check-executables-have-shebangs
      
      # Check shebang scripts
      - id: check-shebang-scripts-are-executable
      
      # Fix requirements.txt
      - id: requirements-txt-fixer


  # ============================================
  # RUFF - Fast Python linter
  # ============================================
  
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.8
    hooks:
      # Linter
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
      
      # Formatter
      - id: ruff-format


  # ============================================
  # BLACK - Code formatter
  # ============================================
  
  - repo: https://github.com/psf/black
    rev: 23.12.1
    hooks:
      - id: black
        language_version: python3.11


  # ============================================
  # ISORT - Import sorter
  # ============================================
  
  - repo: https://github.com/pycqa/isort
    rev: 5.13.2
    hooks:
      - id: isort
        name: isort


  # ============================================
  # MYPY - Static type checker
  # ============================================
  
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.8.0
    hooks:
      - id: mypy
        additional_dependencies:
          - types-redis
          - types-requests
          - types-PyYAML
        args: [--ignore-missing-imports, --show-error-codes]
        exclude: ^(tests/|scripts/)


  # ============================================
  # BANDIT - Security linter
  # ============================================
  
  - repo: https://github.com/PyCQA/bandit
    rev: 1.7.6
    hooks:
      - id: bandit
        args: [-c, pyproject.toml]
        additional_dependencies: ["bandit[toml]"]
        exclude: ^tests/


  # ============================================
  # SAFETY - Check dependencies for vulnerabilities
  # ============================================
  
  - repo: https://github.com/Lucas-C/pre-commit-hooks-safety
    rev: v1.3.3
    hooks:
      - id: python-safety-dependencies-check
        files: requirements.*\.txt$


  # ============================================
  # PRETTIER - Format YAML, JSON, Markdown
  # ============================================
  
  - repo: https://github.com/pre-commit/mirrors-prettier
    rev: v3.1.0
    hooks:
      - id: prettier
        types_or: [yaml, json, markdown]


  # ============================================
  # SHELLCHECK - Shell script linter
  # ============================================
  
  - repo: https://github.com/shellcheck-py/shellcheck-py
    rev: v0.9.0.6
    hooks:
      - id: shellcheck


  # ============================================
  # COMMITIZEN - Commit message linter
  # ============================================
  
  - repo: https://github.com/commitizen-tools/commitizen
    rev: v3.13.0
    hooks:
      - id: commitizen
        stages: [commit-msg]


  # ============================================
  # CUSTOM LOCAL HOOKS
  # ============================================
  
  - repo: local
    hooks:
      # Check for print statements
      - id: check-print-statements
        name: Check for print statements
        entry: python scripts/check_print.py
        language: system
        types: [python]
        exclude: ^(scripts/|tests/)
      
      # Check for TODO comments
      - id: check-todos
        name: Check for TODO comments
        entry: bash -c 'grep -r "TODO" --include="*.py" . && exit 1 || exit 0'
        language: system
        pass_filenames: false
      
      # Run tests
      - id: pytest
        name: Run pytest
        entry: pytest
        language: system
        pass_filenames: false
        stages: [push]  # Only on push, not every commit


# ============================================
# CI (Continuous Integration) Configuration
# ============================================

ci:
  # Auto-update pre-commit hooks
  autoupdate_schedule: weekly
  
  # Skip these hooks in CI
  skip:
    - pytest  # Run separately in CI
    - python-safety-dependencies-check  # Too slow
  
  # Auto-fix pull requests
  autofix_commit_msg: |
    [pre-commit.ci] auto fixes from pre-commit hooks
    
    for more information, see https://pre-commit.ci
  
  autofix_prs: true
  autoupdate_commit_msg: '[pre-commit.ci] pre-commit autoupdate'
2. Custom Pre-commit Hooks
python# scripts/check_print.py

"""
Check for print statements in code

Used as a pre-commit hook
"""

import sys
import ast
from pathlib import Path
from typing import List, Tuple


class PrintChecker(ast.NodeVisitor):
    """AST visitor to find print statements"""
    
    def __init__(self):
        self.print_locations: List[Tuple[int, int]] = []
    
    def visit_Call(self, node: ast.Call):
        """Check if call is a print statement"""
        if isinstance(node.func, ast.Name) and node.func.id == 'print':
            self.print_locations.append((node.lineno, node.col_offset))
        self.generic_visit(node)


def check_file(filepath: Path) -> List[Tuple[int, int]]:
    """
    Check file for print statements
    
    Args:
        filepath: Path to Python file
    
    Returns:
        List of (line, column) tuples
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read(), filename=str(filepath))
        
        checker = PrintChecker()
        checker.visit(tree)
        
        return checker.print_locations
        
    except SyntaxError:
        # File has syntax errors, will be caught by other tools
        return []


def main(files: List[str]) -> int:
    """
    Main function
    
    Args:
        files: List of files to check
    
    Returns:
        0 if no prints found, 1 otherwise
    """
    found_prints = False
    
    for filepath in files:
        path = Path(filepath)
        
        if not path.suffix == '.py':
            continue
        
        print_locations = check_file(path)
        
        if print_locations:
            found_prints = True
            print(f"\n✗ Print statements found in {filepath}:")
            for line, col in print_locations:
                print(f"  Line {line}, Column {col}")
    
    if found_prints:
        print("\n⚠️  Please use logging instead of print statements")
        print("  Example: logger.info('message') instead of print('message')")
        return 1
    
    return 0


if __name__ == '__main__':
    exit_code = main(sys.argv[1:])
    sys.exit(exit_code)
python# scripts/check_todos.py

"""
Check for TODO comments

Used as a pre-commit hook
"""

import sys
import re
from pathlib import Path
from typing import List, Tuple


def find_todos(filepath: Path) -> List[Tuple[int, str]]:
    """
    Find TODO comments in file
    
    Args:
        filepath: Path to file
    
    Returns:
        List of (line_number, todo_text) tuples
    """
    todos = []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, start=1):
                # Match TODO comments
                match = re.search(r'#\s*TODO:?\s*(.+)', line, re.IGNORECASE)
                if match:
                    todos.append((line_num, match.group(1).strip()))
    
    except UnicodeDecodeError:
        # Binary file, skip
        pass
    
    return todos


def main(files: List[str]) -> int:
    """
    Main function
    
    Args:
        files: List of files to check
    
    Returns:
        0 if no TODOs found, 1 otherwise
    """
    found_todos = False
    
    for filepath in files:
        path = Path(filepath)
        
        todos = find_todos(path)
        
        if todos:
            found_todos = True
            print(f"\n✗ TODO comments found in {filepath}:")
            for line_num, todo_text in todos:
                print(f"  Line {line_num}: {todo_text}")
    
    if found_todos:
        print("\n⚠️  Please resolve TODO comments before committing")
        print("  Or create GitHub issues and remove the TODOs")
        return 1
    
    return 0


if __name__ == '__main__':
    exit_code = main(sys.argv[1:])
    sys.exit(exit_code)
3. Pre-commit Installation & Usage
bash# scripts/setup_precommit.sh

#!/bin/bash
# ============================================
# SETUP PRE-COMMIT HOOKS
# ============================================

echo "Setting up pre-commit hooks..."
echo ""

# Install pre-commit
echo "Installing pre-commit..."
pip install pre-commit
echo "✓ pre-commit installed"
echo ""

# Install hooks
echo "Installing git hooks..."
pre-commit install

# Also install commit-msg hook for commitizen
pre-commit install --hook-type commit-msg

echo "✓ Git hooks installed"
echo ""

# Update hooks
echo "Updating hooks to latest versions..."
pre-commit autoupdate
echo "✓ Hooks updated"
echo ""

# Run on all files (optional)
read -p "Run pre-commit on all files now? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Running pre-commit on all files..."
    pre-commit run --all-files
    echo "✓ Pre-commit run complete"
fi

echo ""
echo "✓ Pre-commit setup complete!"
echo ""
echo "Pre-commit will now run automatically on git commit"
echo ""
echo "Useful commands:"
echo "  pre-commit run --all-files  # Run on all files"
echo "  pre-commit run <hook-id>    # Run specific hook"
echo "  git commit --no-verify      # Skip pre-commit hooks"
bash# Manual pre-commit commands

# Install pre-commit
pip install pre-commit

# Install git hooks
pre-commit install
pre-commit install --hook-type commit-msg

# Run on all files
pre-commit run --all-files

# Run specific hook
pre-commit run black
pre-commit run mypy

# Update hooks
pre-commit autoupdate

# Clean cache
pre-commit clean

# Uninstall hooks
pre-commit uninstall

# Skip hooks for one commit
git commit --no-verify -m "message"

# Run manually without git
pre-commit run --files file1.py file2.py
4. GitHub Actions Integration
yaml# .github/workflows/code-quality.yml

name: Code Quality

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  # ============================================
  # PRE-COMMIT CHECKS
  # ============================================
  
  pre-commit:
    name: Pre-commit Checks
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install pre-commit
        run: pip install pre-commit
      
      - name: Cache pre-commit
        uses: actions/cache@v3
        with:
          path: ~/.cache/pre-commit
          key: pre-commit-${{ hashFiles('.pre-commit-config.yaml') }}
      
      - name: Run pre-commit
        run: pre-commit run --all-files --show-diff-on-failure


  # ============================================
  # LINTING
  # ============================================
  
  lint:
    name: Linting
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install ruff flake8 pylint
          pip install -r requirements.txt
      
      - name: Run Ruff
        run: ruff check .
      
      - name: Run Flake8
        run: flake8 .
      
      - name: Run Pylint
        run: pylint models services api


  # ============================================
  # TYPE CHECKING
  # ============================================
  
  type-check:
    name: Type Checking
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install mypy
          pip install -r requirements.txt
          pip install types-redis types-requests
      
      - name: Run mypy
        run: mypy .


  # ============================================
  # FORMATTING CHECK
  # ============================================
  
  format-check:
    name: Format Check
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: pip install black isort
      
      - name: Check with Black
        run: black . --check
      
      - name: Check with isort
        run: isort . --check-only


  # ============================================
  # SECURITY CHECK
  # ============================================
  
  security:
    name: Security Check
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install bandit safety
          pip install -r requirements.txt
      
      - name: Run Bandit
        run: bandit -r . -f json -o bandit-report.json
      
      - name: Run Safety
        run: safety check --json
      
      - name: Upload security reports
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: security-reports
          path: |
            bandit-report.json

👀 CODE REVIEW GUIDELINES
1. Code Review Checklist
markdown# CODE REVIEW CHECKLIST
# ============================================

## Before Submitting for Review

### ✅ Code Quality
- [ ] Code follows PEP 8 style guide
- [ ] All linters pass (Ruff, Flake8, Pylint)
- [ ] Type hints are present and mypy passes
- [ ] Code is formatted with Black and isort
- [ ] Pre-commit hooks pass

### ✅ Testing
- [ ] Unit tests written for new code
- [ ] All tests pass
- [ ] Test coverage is adequate (>80%)
- [ ] Integration tests updated if needed

### ✅ Documentation
- [ ] Docstrings added/updated
- [ ] README updated if needed
- [ ] API documentation updated
- [ ] Changelog updated

### ✅ Security
- [ ] No secrets in code
- [ ] Input validation present
- [ ] SQL injection prevention
- [ ] XSS prevention
- [ ] Authentication/authorization correct

### ✅ Performance
- [ ] No obvious performance issues
- [ ] Database queries optimized
- [ ] Caching implemented where appropriate
- [ ] No N+1 query problems

### ✅ Git
- [ ] Commits are atomic and well-described
- [ ] Branch is up to date with main
- [ ] No merge conflicts
- [ ] Commit messages follow convention


## During Code Review

### 🔍 Functionality
- [ ] Code does what it's supposed to do
- [ ] Edge cases handled
- [ ] Error handling is appropriate
- [ ] No obvious bugs

### 🏗️ Design
- [ ] Code is maintainable
- [ ] Follows existing patterns
- [ ] No code duplication
- [ ] Proper separation of concerns
- [ ] SOLID principles followed

### 📖 Readability
- [ ] Code is easy to understand
- [ ] Variable names are descriptive
- [ ] Functions are focused and small
- [ ] Comments explain "why", not "what"

### 🧪 Testing
- [ ] Tests are comprehensive
- [ ] Tests are readable
- [ ] Tests follow AAA pattern (Arrange, Act, Assert)
- [ ] Edge cases tested

### 🔒 Security
- [ ] Input validation
- [ ] Output encoding
- [ ] Authentication checks
- [ ] Authorization checks
- [ ] Sensitive data handling

### ⚡ Performance
- [ ] No unnecessary computations
- [ ] Efficient algorithms
- [ ] Proper indexing
- [ ] Caching where appropriate

### 📚 Documentation
- [ ] Public APIs documented
- [ ] Complex logic explained
- [ ] Examples provided where helpful


## Review Response

### ✅ For Reviewers
- [ ] Be constructive and kind
- [ ] Explain reasoning
- [ ] Suggest alternatives
- [ ] Approve or request changes clearly

### ✅ For Authors
- [ ] Respond to all comments
- [ ] Ask for clarification if needed
- [ ] Make requested changes
- [ ] Mark conversations as resolved
2. Review Comment Templates
python# code_review_templates.py

"""
Code Review Comment Templates

Use these templates for common review scenarios
"""

# ============================================
# POSITIVE FEEDBACK
# ============================================

POSITIVE_TEMPLATES = {
    "good_pattern": """
    ✓ Nice use of [pattern/technique]! This makes the code much more [maintainable/readable/efficient].
    """,
    
    "good_test": """
    ✓ Great test coverage! I especially like how you tested [edge case/scenario].
    """,
    
    "good_naming": """
    ✓ Excellent variable/function naming. Very clear what [variable/function] does.
    """,
    
    "good_refactor": """
    ✓ This refactoring significantly improves [readability/performance/maintainability].
    """,
}

# ============================================
# IMPROVEMENT SUGGESTIONS
# ============================================

IMPROVEMENT_TEMPLATES = {
    "complexity": """
    💡 This function is quite complex (cyclomatic complexity: X). Consider breaking it down:
```python
    # Current
    def complex_function():
        # 50 lines of code
        pass
    
    # Suggested
    def main_function():
        step1_result = _do_step1()
        step2_result = _do_step2(step1_result)
        return _do_step3(step2_result)
    
    def _do_step1():
        # Focused logic
        pass
```
    """,
    
    "type_hints": """
    💡 Please add type hints for better code clarity:
```python
    # Current
    def process_data(data):
        return result
    
    # Suggested
    def process_data(data: List[Dict[str, Any]]) -> ProcessedData:
        return result
```
    """,
    
    "error_handling": """
    💡 Consider adding error handling for [scenario]:
```python
    # Current
    result = risky_operation()
    
    # Suggested
    try:
        result = risky_operation()
    except SpecificError as e:
        logger.error(f"Operation failed: {e}")
        # Handle appropriately
```
    """,
    
    "performance": """
    💡 This could be more efficient. Consider:
```python
    # Current (O(n²))
    for item in items:
        if item in other_items:  # List lookup
            process(item)
    
    # Suggested (O(n))
    other_items_set = set(other_items)
    for item in items:
        if item in other_items_set:  # Set lookup
            process(item)
```
    """,
    
    "naming": """
    💡 The name `x` is not very descriptive. Consider renaming to something like `user_count` or `processed_items` to better indicate what it represents.
    """,
    
    "docstring": """
    💡 Please add a docstring explaining:
    - What this function does
    - Parameters and their types
    - Return value
    - Any exceptions raised
```python
    def example_function(param: str) -> dict:
        \"\"\"
        Brief description.
        
        Args:
            param: Description of param
        
        Returns:
            Dictionary containing results
        
        Raises:
            ValueError: When param is invalid
        \"\"\"
```
    """,
}

# ============================================
# BLOCKING ISSUES
# ============================================

BLOCKING_TEMPLATES = {
    "security": """
    🚨 SECURITY ISSUE: This code is vulnerable to [type of vulnerability].
    
    This must be fixed before merging:
```python
    # Current (vulnerable)
    query = f"SELECT * FROM users WHERE id = {user_id}"
    
    # Fix (use parameterized query)
    query = "SELECT * FROM users WHERE id = ?"
    cursor.execute(query, (user_id,))
```
    
    References:
    - [Link to security best practices]
    """,
    
    "bug": """
    🐛 BUG: This will cause [issue] when [condition].
    
    Steps to reproduce:
    1. [Step 1]
    2. [Step 2]
    
    Expected: [Expected behavior]
    Actual: [Actual behavior]
    
    Suggested fix:
```python
    # Fix
```
    """,
    
    "breaking_change": """
    ⚠️  BREAKING CHANGE: This modifies the public API.
    
    Before merging:
    1. Update version number (major bump)
    2. Update migration guide
    3. Notify users
    4. Update documentation
    """,
}

# ============================================
# QUESTIONS
# ============================================

QUESTION_TEMPLATES = {
    "clarification": """
    ❓ Can you clarify why [decision] was made here? I'm wondering if [alternative approach] might be better because [reason].
    """,
    
    "test_case": """
    ❓ Have you considered the case where [scenario]? It might be good to add a test for this.
    """,
    
    "alternative": """
    ❓ What do you think about using [alternative approach]? It might [benefit] because [reason].
    """,
}
3. Pull Request Template
markdown# .github/pull_request_template.md

## Description
<!-- Brief description of what this PR does -->

## Type of Change
<!-- Mark the relevant option with an "x" -->

- [ ] 🐛 Bug fix (non-breaking change which fixes an issue)
- [ ] ✨ New feature (non-breaking change which adds functionality)
- [ ] 💥 Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] 📝 Documentation update
- [ ] 🎨 Code style update (formatting, renaming)
- [ ] ♻️  Refactoring (no functional changes)
- [ ] ⚡ Performance improvement
- [ ] ✅ Test update
- [ ] 🔧 Build/CI update
- [ ] 🔒 Security update

## Related Issues
<!-- Link to related issues -->

Fixes #(issue number)
Relates to #(issue number)

## Changes Made
<!-- List the main changes -->

- Change 1
- Change 2
- Change 3

## Testing
<!-- Describe the tests you ran -->

- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Manual testing completed

### Test Coverage
<!-- If applicable -->

- Before: X%
- After: Y%

## Screenshots
<!-- If applicable, add screenshots -->

## Checklist

### Code Quality
- [ ] Code follows PEP 8 style guide
- [ ] Type hints added
- [ ] Docstrings updated
- [ ] Linters pass (Ruff, Flake8, Pylint)
- [ ] mypy passes
- [ ] Pre-commit hooks pass

### Testing
- [ ] Tests added/updated
- [ ] All tests pass
- [ ] Test coverage adequate (>80%)

### Documentation
- [ ] README updated
- [ ] API docs updated
- [ ] Changelog updated
- [ ] Comments added for complex logic

### Security
- [ ] No secrets in code
- [ ] Input validation added
- [ ] Security scan passed

### Performance
- [ ] No performance regressions
- [ ] Database queries optimized
- [ ] Caching implemented if needed

## Additional Notes
<!-- Any additional information for reviewers -->

## Reviewer Notes
<!-- For reviewers: Areas you should focus on -->

Please pay special attention to:
- [ ] Area 1
- [ ] Area 2

CODE QUALITY & STANDARDS GUIDE - TEIL 3 (FINAL)
Documentation Standards, CI/CD & Complete Setup

📋 TABLE OF CONTENTS (TEIL 3)

Documentation Standards
CI/CD Integration
Complete Setup Guide
Best Practices Summary


📚 DOCUMENTATION STANDARDS
1. Docstring Standards
python# docstring_examples.py

"""
Documentation Standards Examples

Following Google-style docstrings
"""

from typing import List, Dict, Optional, Any
from datetime import datetime


# ============================================
# MODULE DOCSTRING
# ============================================

"""
Module for OCR processing operations.

This module provides comprehensive OCR capabilities including:
- Document text extraction
- Multi-language support
- Format conversion
- Quality assessment

Example:
    >>> from services.ocr import OCRProcessor
    >>> processor = OCRProcessor()
    >>> result = processor.process_document("document.pdf")
    >>> print(result.text)

Attributes:
    DEFAULT_LANGUAGE (str): Default language for OCR
    MAX_FILE_SIZE (int): Maximum file size in bytes
"""

DEFAULT_LANGUAGE = "de"
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB


# ============================================
# CLASS DOCSTRING
# ============================================

class OCRProcessor:
    """
    OCR processing engine for document analysis.
    
    This class handles the complete OCR workflow including preprocessing,
    text extraction, post-processing, and quality validation. It supports
    multiple OCR backends and automatic fallback mechanisms.
    
    The processor uses a multi-backend architecture:
    1. GPU Backend A (DeepSeek-Janus-Pro) for complex documents
    2. GPU Backend B (GOT-OCR 2.0) for simple documents
    3. CPU Backend (Surya + Docling) as fallback
    
    Attributes:
        language: OCR language code (ISO 639-1)
        gpu_enabled: Whether GPU acceleration is available
        cache_enabled: Whether result caching is enabled
        backends: List of initialized OCR backends
    
    Example:
        >>> processor = OCRProcessor(language="de", gpu_enabled=True)
        >>> result = processor.process_document(
        ...     file_path="invoice.pdf",
        ...     document_type="invoice"
        ... )
        >>> print(f"Confidence: {result.confidence}%")
        Confidence: 98.5%
    
    Note:
        GPU backends require CUDA 11.8+ and appropriate drivers.
        CPU fallback is always available regardless of hardware.
    
    See Also:
        - :class:`OCRResult`: Result data structure
        - :class:`DocumentPreprocessor`: Image preprocessing
        - :func:`validate_ocr_output`: Output validation
    """
    
    def __init__(
        self,
        language: str = "de",
        gpu_enabled: bool = True,
        cache_enabled: bool = True
    ) -> None:
        """
        Initialize OCR processor.
        
        Args:
            language: Language code for OCR (ISO 639-1).
                Defaults to "de" (German).
            gpu_enabled: Enable GPU acceleration if available.
                Falls back to CPU if GPU not found.
            cache_enabled: Enable result caching for repeated
                processing of same documents.
        
        Raises:
            ValueError: If language code is invalid.
            RuntimeError: If no backends could be initialized.
        
        Example:
            >>> # Basic initialization
            >>> processor = OCRProcessor()
            >>> 
            >>> # Custom configuration
            >>> processor = OCRProcessor(
            ...     language="en",
            ...     gpu_enabled=False,
            ...     cache_enabled=True
            ... )
        """
        self.language = language
        self.gpu_enabled = gpu_enabled
        self.cache_enabled = cache_enabled
        self.backends: List[OCRBackend] = []
        
        self._initialize_backends()
    
    def process_document(
        self,
        file_path: str,
        document_type: Optional[str] = None,
        preprocessing: bool = True
    ) -> OCRResult:
        """
        Process document and extract text via OCR.
        
        This method orchestrates the complete OCR pipeline:
        1. File validation and format detection
        2. Image preprocessing (if enabled)
        3. Backend selection based on complexity
        4. OCR execution with fallback handling
        5. Post-processing and quality validation
        
        Args:
            file_path: Path to document file. Supports PDF, PNG, JPG,
                TIFF formats.
            document_type: Optional document type hint for optimization.
                Valid values: "invoice", "contract", "letter", "form".
                If None, type is auto-detected.
            preprocessing: Whether to apply image preprocessing.
                Includes deskewing, noise removal, and contrast
                enhancement. Recommended for scanned documents.
        
        Returns:
            OCRResult object containing:
                - text: Extracted text content
                - confidence: Overall confidence score (0-100)
                - language: Detected language
                - page_count: Number of pages processed
                - metadata: Additional processing metadata
        
        Raises:
            FileNotFoundError: If file_path does not exist.
            ValueError: If file format is not supported.
            OCRProcessingError: If all backends fail to process.
            MemoryError: If document is too large for available RAM.
        
        Example:
            >>> # Basic usage
            >>> result = processor.process_document("invoice.pdf")
            >>> print(result.text)
            
            >>> # With document type hint
            >>> result = processor.process_document(
            ...     file_path="contract.pdf",
            ...     document_type="contract",
            ...     preprocessing=True
            ... )
            >>> if result.confidence > 95:
            ...     save_to_database(result)
        
        Note:
            Processing time varies by document complexity:
            - Simple documents: 1-3 seconds
            - Complex documents: 5-15 seconds
            - Large multi-page documents: 30-60 seconds
        
        Warning:
            Large documents (>50 pages) may consume significant
            memory. Consider splitting into smaller chunks.
        
        See Also:
            - :meth:`process_batch`: For batch processing
            - :meth:`validate_result`: For result validation
        """
        # Implementation
        pass
    
    def process_batch(
        self,
        file_paths: List[str],
        parallel: bool = True,
        max_workers: int = 4
    ) -> List[OCRResult]:
        """
        Process multiple documents in batch.
        
        Efficiently processes multiple documents with optional
        parallel execution. Automatically balances load across
        available backends and handles individual failures gracefully.
        
        Args:
            file_paths: List of paths to document files.
                All files must exist and be in supported formats.
            parallel: Enable parallel processing using thread pool.
                Significantly faster for multiple documents.
                Set to False for sequential processing.
            max_workers: Maximum number of parallel workers.
                Defaults to 4. Adjust based on available CPU/GPU.
                Higher values may cause memory pressure.
        
        Returns:
            List of OCRResult objects, one per input file.
            Order matches input file_paths order.
            Failed documents return OCRResult with error flag.
        
        Raises:
            ValueError: If file_paths is empty.
            MemoryError: If batch is too large for available memory.
        
        Example:
            >>> # Process multiple invoices
            >>> files = [
            ...     "invoice1.pdf",
            ...     "invoice2.pdf",
            ...     "invoice3.pdf"
            ... ]
            >>> results = processor.process_batch(
            ...     file_paths=files,
            ...     parallel=True,
            ...     max_workers=4
            ... )
            >>> 
            >>> # Check results
            >>> for file, result in zip(files, results):
            ...     if result.success:
            ...         print(f"{file}: {result.confidence}%")
            ...     else:
            ...         print(f"{file}: FAILED - {result.error}")
        
        Note:
            Parallel processing is most beneficial for:
            - 3+ documents
            - Documents requiring similar processing time
            - Systems with multiple CPU cores
            
            Sequential processing is better for:
            - 1-2 documents
            - Very large documents (memory constraint)
            - Systems with limited cores
        
        Performance:
            Typical batch processing times (4 workers, GPU enabled):
            - 10 documents: 15-30 seconds
            - 50 documents: 60-120 seconds
            - 100 documents: 150-300 seconds
        """
        # Implementation
        pass
    
    @staticmethod
    def validate_result(result: OCRResult) -> bool:
        """
        Validate OCR result quality.
        
        Performs comprehensive validation including:
        - Text length validation
        - Confidence threshold check
        - Language consistency check
        - Character set validation
        
        Args:
            result: OCRResult object to validate.
        
        Returns:
            True if result passes all validation checks,
            False otherwise.
        
        Example:
            >>> result = processor.process_document("doc.pdf")
            >>> if OCRProcessor.validate_result(result):
            ...     save_to_database(result)
            ... else:
            ...     flag_for_manual_review(result)
        """
        # Implementation
        pass
    
    def _initialize_backends(self) -> None:
        """
        Initialize OCR backends.
        
        Private method to set up available OCR backends based on
        hardware capabilities and configuration. Attempts to
        initialize in priority order: GPU backends first, then
        CPU fallback.
        
        Raises:
            RuntimeError: If no backends could be initialized.
        
        Note:
            This is a private method, not part of the public API.
        """
        # Implementation
        pass


# ============================================
# FUNCTION DOCSTRING - SIMPLE
# ============================================

def calculate_confidence(
    text: str,
    language: str
) -> float:
    """
    Calculate OCR confidence score.
    
    Args:
        text: Extracted text
        language: Language code
    
    Returns:
        Confidence score between 0 and 100
    
    Example:
        >>> score = calculate_confidence("Hello World", "en")
        >>> print(score)
        98.5
    """
    # Implementation
    pass


# ============================================
# FUNCTION DOCSTRING - COMPLEX
# ============================================

def preprocess_image(
    image_path: str,
    output_path: Optional[str] = None,
    deskew: bool = True,
    denoise: bool = True,
    enhance_contrast: bool = True,
    target_dpi: int = 300
) -> str:
    """
    Preprocess image for optimal OCR results.
    
    Applies a series of image enhancements to improve OCR accuracy:
    1. DPI normalization to target resolution
    2. Deskewing to correct rotation
    3. Noise removal using adaptive filters
    4. Contrast enhancement via histogram equalization
    
    The preprocessing pipeline is optimized for scanned documents
    and handles various input qualities gracefully.
    
    Args:
        image_path: Path to input image file.
            Supported formats: PNG, JPG, TIFF, BMP.
        output_path: Optional path for preprocessed output.
            If None, creates temp file. Original is never modified.
        deskew: Apply automatic deskewing to correct rotation.
            Uses Hough transform to detect document edges.
            Recommended for scanned documents.
        denoise: Apply noise removal filters.
            Uses bilateral filter to preserve edges while
            removing noise. Especially useful for poor quality scans.
        enhance_contrast: Enhance image contrast.
            Uses CLAHE (Contrast Limited Adaptive Histogram
            Equalization) for better text visibility.
        target_dpi: Target DPI for output image.
            300 DPI recommended for optimal OCR. Higher DPI
            increases processing time without significant accuracy gain.
    
    Returns:
        Path to preprocessed image file.
        If output_path was provided, returns that path.
        Otherwise returns path to temporary file.
    
    Raises:
        FileNotFoundError: If image_path does not exist.
        ValueError: If image format is not supported or
            target_dpi is out of valid range (72-600).
        IOError: If image cannot be read or written.
    
    Example:
        >>> # Basic preprocessing
        >>> output = preprocess_image("scan.jpg")
        >>> 
        >>> # Custom preprocessing
        >>> output = preprocess_image(
        ...     image_path="low_quality_scan.tiff",
        ...     output_path="preprocessed.png",
        ...     deskew=True,
        ...     denoise=True,
        ...     enhance_contrast=True,
        ...     target_dpi=400
        ... )
        >>> result = processor.process_document(output)
    
    Note:
        Processing time scales with image size:
        - Small images (<1MP): <1 second
        - Medium images (1-5MP): 1-3 seconds
        - Large images (>5MP): 3-10 seconds
    
    Warning:
        Very high DPI (>600) may cause:
        - Excessive processing time
        - High memory usage
        - Diminishing accuracy returns
    
    See Also:
        - :func:`detect_dpi`: Detect current image DPI
        - :func:`optimize_for_ocr`: Auto-optimize settings
    """
    # Implementation
    pass


# ============================================
# EXCEPTION DOCSTRING
# ============================================

class OCRProcessingError(Exception):
    """
    Exception raised when OCR processing fails.
    
    This exception is raised when all OCR backends fail to
    process a document, or when a critical error occurs
    during processing that cannot be recovered.
    
    Attributes:
        message: Human-readable error description
        file_path: Path to the document that failed
        backend: Name of backend that raised the error
        original_error: Original exception that was caught
    
    Example:
        >>> try:
        ...     result = processor.process_document("corrupt.pdf")
        ... except OCRProcessingError as e:
        ...     logger.error(f"OCR failed: {e.message}")
        ...     logger.debug(f"Backend: {e.backend}")
        ...     logger.debug(f"Original error: {e.original_error}")
    """
    
    def __init__(
        self,
        message: str,
        file_path: str,
        backend: Optional[str] = None,
        original_error: Optional[Exception] = None
    ):
        """
        Initialize OCRProcessingError.
        
        Args:
            message: Error description
            file_path: Path to failed document
            backend: Optional backend identifier
            original_error: Optional original exception
        """
        self.message = message
        self.file_path = file_path
        self.backend = backend
        self.original_error = original_error
        super().__init__(self.message)


# ============================================
# DATA CLASS DOCSTRING
# ============================================

from dataclasses import dataclass

@dataclass
class OCRResult:
    """
    OCR processing result data.
    
    Contains all information about an OCR processing operation
    including extracted text, confidence metrics, metadata,
    and processing statistics.
    
    Attributes:
        text: Extracted text content
        confidence: Overall confidence score (0-100)
        language: Detected language code (ISO 639-1)
        page_count: Number of pages processed
        processing_time: Time taken in seconds
        backend_used: Name of backend that processed document
        metadata: Additional processing metadata
        success: Whether processing succeeded
        error: Error message if processing failed
    
    Example:
        >>> result = OCRResult(
        ...     text="Extracted text content",
        ...     confidence=98.5,
        ...     language="de",
        ...     page_count=1,
        ...     processing_time=2.3,
        ...     backend_used="deepseek",
        ...     metadata={"dpi": 300},
        ...     success=True
        ... )
        >>> print(result.text)
        Extracted text content
    """
    
    text: str
    confidence: float
    language: str
    page_count: int
    processing_time: float
    backend_used: str
    metadata: Dict[str, Any]
    success: bool = True
    error: Optional[str] = None
2. API Documentation
python# api/docs.py

"""
API Documentation Configuration

FastAPI automatic documentation with custom descriptions
"""

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi


# ============================================
# API METADATA
# ============================================

API_METADATA = {
    "title": "OCR Processing API",
    "description": """
# OCR Processing API

Professional OCR (Optical Character Recognition) service for German business documents.

## Features

* 🚀 **Multi-Backend Architecture**: GPU-accelerated and CPU fallback
* 🇩🇪 **German Language Optimized**: Perfect umlaut recognition
* 📄 **Multiple Formats**: PDF, PNG, JPG, TIFF support
* ⚡ **High Performance**: Batch processing and caching
* 🔒 **Enterprise Security**: Authentication and encryption
* 📊 **Quality Metrics**: Confidence scores and validation

## Quick Start

1. **Authentication**: Obtain API key from `/auth/register`
2. **Upload Document**: POST to `/documents/upload`
3. **Process**: POST to `/ocr/process/{document_id}`
4. **Retrieve**: GET from `/documents/{document_id}/result`

## Rate Limits

- Free tier: 100 requests/day
- Pro tier: 1000 requests/day
- Enterprise: Unlimited

## Support

- Documentation: https://docs.example.com
- Email: support@example.com
- Status: https://status.example.com

## Version History

### v1.2.0 (Current)
- Added batch processing
- Improved German umlaut recognition
- Performance optimizations

### v1.1.0
- Multi-backend support
- Caching layer
- Enhanced error handling
""",
    "version": "1.2.0",
    "contact": {
        "name": "OCR API Support",
        "email": "support@example.com",
        "url": "https://example.com/support"
    },
    "license_info": {
        "name": "Commercial License",
        "url": "https://example.com/license"
    }
}


# ============================================
# TAG METADATA
# ============================================

TAGS_METADATA = [
    {
        "name": "authentication",
        "description": """
        User authentication and authorization operations.
        
        Endpoints for user registration, login, token management,
        and permission control.
        """,
    },
    {
        "name": "documents",
        "description": """
        Document management operations.
        
        Upload, retrieve, update, and delete documents. Includes
        metadata management and file versioning.
        """,
    },
    {
        "name": "ocr",
        "description": """
        OCR processing operations.
        
        Process documents using OCR engines. Supports single and
        batch processing, multiple languages, and quality validation.
        """,
    },
    {
        "name": "users",
        "description": """
        User management operations.
        
        Manage user accounts, profiles, and preferences.
        Admin-only endpoints for user administration.
        """,
    },
]


# ============================================
# CUSTOM OPENAPI SCHEMA
# ============================================

def custom_openapi(app: FastAPI):
    """
    Generate custom OpenAPI schema
    
    Args:
        app: FastAPI application instance
    
    Returns:
        OpenAPI schema dictionary
    """
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title=API_METADATA["title"],
        version=API_METADATA["version"],
        description=API_METADATA["description"],
        routes=app.routes,
        tags=TAGS_METADATA,
        contact=API_METADATA["contact"],
        license_info=API_METADATA["license_info"],
    )
    
    # Add security schemes
    openapi_schema["components"]["securitySchemes"] = {
        "Bearer": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Enter your JWT token"
        },
        "APIKey": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": "Enter your API key"
        }
    }
    
    # Add example responses
    openapi_schema["components"]["examples"] = {
        "OCRResultExample": {
            "value": {
                "text": "Rechnung\nRechnungsnummer: 2024-001",
                "confidence": 98.5,
                "language": "de",
                "page_count": 1,
                "processing_time": 2.3
            }
        }
    }
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema


# ============================================
# API ENDPOINT DOCUMENTATION EXAMPLE
# ============================================

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/ocr", tags=["ocr"])


class ProcessRequest(BaseModel):
    """
    OCR processing request model.
    
    Attributes:
        document_id: Unique document identifier
        language: Language code for OCR
        preprocessing: Enable image preprocessing
        document_type: Optional document type hint
    """
    
    document_id: str = Field(
        ...,
        description="Unique document identifier",
        example="doc_abc123xyz"
    )
    language: str = Field(
        default="de",
        description="Language code (ISO 639-1)",
        example="de",
        min_length=2,
        max_length=2
    )
    preprocessing: bool = Field(
        default=True,
        description="Apply image preprocessing"
    )
    document_type: Optional[str] = Field(
        None,
        description="Document type hint for optimization",
        example="invoice"
    )
    
    class Config:
        schema_extra = {
            "example": {
                "document_id": "doc_abc123xyz",
                "language": "de",
                "preprocessing": True,
                "document_type": "invoice"
            }
        }


@router.post(
    "/process",
    summary="Process document with OCR",
    description="""
    Process a document using OCR to extract text.
    
    This endpoint processes a previously uploaded document and
    extracts text using our multi-backend OCR system.
    
    ## Process Flow
    
    1. Validate document exists
    2. Select optimal backend based on document complexity
    3. Apply preprocessing if enabled
    4. Execute OCR extraction
    5. Validate and return results
    
    ## Backend Selection
    
    - **Simple documents**: GOT-OCR 2.0 (fast, GPU)
    - **Complex documents**: DeepSeek-Janus-Pro (accurate, GPU)
    - **Fallback**: Surya + Docling (CPU)
    
    ## Performance
    
    - Simple documents: 1-3 seconds
    - Complex documents: 5-15 seconds
    - Large documents (50+ pages): 30-60 seconds
    
    ## Quality Assurance
    
    Results include confidence scores. Recommendations:
    - 95%+: Excellent quality, ready for production
    - 85-95%: Good quality, minor review recommended
    - 70-85%: Fair quality, review recommended
    - <70%: Poor quality, manual verification required
    """,
    response_description="OCR processing result with extracted text",
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Successfully processed document",
            "content": {
                "application/json": {
                    "example": {
                        "text": "Rechnung\nRechnungsnummer: 2024-001",
                        "confidence": 98.5,
                        "language": "de",
                        "page_count": 1,
                        "processing_time": 2.3,
                        "backend_used": "deepseek",
                        "metadata": {
                            "dpi": 300,
                            "format": "pdf"
                        }
                    }
                }
            }
        },
        400: {
            "description": "Invalid request",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Invalid language code"
                    }
                }
            }
        },
        404: {
            "description": "Document not found",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Document with ID 'doc_abc123' not found"
                    }
                }
            }
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Rate limit exceeded. Try again in 60 seconds"
                    }
                }
            }
        },
        500: {
            "description": "Processing error",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "OCR processing failed. All backends unavailable"
                    }
                }
            }
        }
    }
)
async def process_document(
    request: ProcessRequest,
    current_user = Depends(get_current_user)
):
    """
    Process document with OCR.
    
    Full documentation in endpoint description above.
    """
    # Implementation
    pass
3. README Documentation
markdown# README.md

# 🚀 OCR Processing System

Professional OCR (Optical Character Recognition) system for German business documents with perfect umlaut recognition.

[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104-green.svg)](https://fastapi.tiangolo.com/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Type checked: mypy](https://img.shields.io/badge/type%20checked-mypy-blue.svg)](http://mypy-lang.org/)
[![License: Commercial](https://img.shields.io/badge/license-Commercial-red.svg)](LICENSE)

## 📋 Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [API Documentation](#api-documentation)
- [Development](#development)
- [Testing](#testing)
- [Deployment](#deployment)
- [Contributing](#contributing)
- [License](#license)

## ✨ Features

### Core Features
- 🎯 **Multi-Backend OCR**: GPU and CPU support
- 🇩🇪 **German Optimized**: Perfect umlaut (ä, ö, ü, ß) recognition
- 📄 **Multiple Formats**: PDF, PNG, JPG, TIFF
- ⚡ **High Performance**: Batch processing, caching
- 🔒 **Enterprise Security**: JWT auth, encryption
- 📊 **Quality Metrics**: Confidence scores, validation

### OCR Backends
1. **GPU Backend A**: DeepSeek-Janus-Pro (complex documents)
2. **GPU Backend B**: GOT-OCR 2.0 (simple documents, speed)
3. **CPU Backend**: Surya + Docling (fallback, always available)

## 🏗️ Architecture
```
┌─────────────────────────────────────────┐
│           FastAPI Application           │
├─────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌────────┐│
│  │   API    │  │  Auth    │  │  Docs  ││
│  │  Routes  │  │  Layer   │  │  Layer ││
│  └──────────┘  └──────────┘  └────────┘│
├─────────────────────────────────────────┤
│         OCR Processing Layer            │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐ │
│  │ GPU-A   │  │ GPU-B   │  │ CPU     │ │
│  │DeepSeek │  │GOT-OCR  │  │ Surya   │ │
│  └─────────┘  └─────────┘  └─────────┘ │
├─────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌────────┐│
│  │PostgreSQL│  │  Redis   │  │ Celery ││
│  │    DB    │  │  Cache   │  │ Tasks  ││
│  └──────────┘  └──────────┘  └────────┘│
└─────────────────────────────────────────┘
```

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- NVIDIA GPU with CUDA 11.8+ (optional, for GPU backends)
- PostgreSQL 15+
- Redis 7+

### Installation
```bash
# Clone repository
git clone https://github.com/yourorg/ocr-system.git
cd ocr-system

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Setup pre-commit hooks
pre-commit install

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Run database migrations
alembic upgrade head

# Start application
uvicorn main:app --reload
```

### Docker Quick Start
```bash
# Start all services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f app

# Stop services
docker-compose down
```

## ⚙️ Configuration

### Environment Variables
```bash
# Application
APP_NAME=OCR Processing System
APP_ENV=development
DEBUG=true

# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/ocr_db

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=your_password

# OCR Settings
OCR_DEFAULT_LANGUAGE=de
OCR_MAX_FILE_SIZE=104857600  # 100MB
OCR_GPU_ENABLED=true

# Security
SECRET_KEY=your-secret-key-here
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

See [.env.example](.env.example) for all options.

## 📖 Usage

### Python SDK
```python
from ocr_client import OCRClient

# Initialize client
client = OCRClient(
    api_key="your-api-key",
    base_url="http://localhost:8000"
)

# Process document
result = client.process_document(
    file_path="invoice.pdf",
    language="de",
    document_type="invoice"
)

print(f"Text: {result.text}")
print(f"Confidence: {result.confidence}%")
```

### REST API
```bash
# Upload document
curl -X POST "http://localhost:8000/documents/upload" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@invoice.pdf"

# Process with OCR
curl -X POST "http://localhost:8000/ocr/process" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "document_id": "doc_123",
    "language": "de",
    "preprocessing": true
  }'

# Get result
curl -X GET "http://localhost:8000/documents/doc_123/result" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### CLI
```bash
# Process single document
ocr process invoice.pdf --language de --output result.txt

# Batch processing
ocr batch ./documents/*.pdf --parallel --workers 4

# Get status
ocr status doc_123
```

## 📚 API Documentation

Interactive API documentation available at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 🛠️ Development

### Code Quality
```bash
# Format code
make format

# Run linters
make lint

# Type checking
make type-check

# All quality checks
make quality-check
```

### Testing
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific tests
pytest tests/test_ocr.py

# Run integration tests
pytest tests/integration/
```

### Database Migrations
```bash
# Create migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

## 🚢 Deployment

### Production Checklist

- [ ] Set `APP_ENV=production`
- [ ] Change all default passwords
- [ ] Configure SSL certificates
- [ ] Set up monitoring (Prometheus/Grafana)
- [ ] Configure backup strategy
- [ ] Set up logging aggregation
- [ ] Configure rate limiting
- [ ] Enable CORS properly
- [ ] Set up CDN for static files
- [ ] Configure health checks

### Docker Production
```bash
# Build production image
docker build -t ocr-system:latest .

# Run with production config
docker-compose -f docker-compose.prod.yml up -d

# Scale workers
docker-compose -f docker-compose.prod.yml up -d --scale worker=4
```

## 🤝 Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details.

### Development Workflow

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests and quality checks
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## 📄 License

This project is licensed under a Commercial License - see [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- DeepSeek for Janus-Pro model
- GOT-OCR team for GOT-OCR 2.0
- Surya OCR team
- FastAPI framework
- All contributors

## 📞 Support

- 📧 Email: support@example.com
- 💬 Discord: https://discord.gg/example
- 📖 Documentation: https://docs.example.com
- 🐛 Issue Tracker: https://github.com/yourorg/ocr-system/issues

## 🗺️ Roadmap

### Version 1.3 (Q2 2024)
- [ ] Support for more languages
- [ ] Enhanced batch processing
- [ ] Improved caching strategy
- [ ] Real-time processing status

### Version 2.0 (Q3 2024)
- [ ] Machine learning-based quality prediction
- [ ] Advanced preprocessing options
- [ ] Custom model training
- [ ] Multi-tenant support

---

Made with ❤️ by Your Company

🔄 CI/CD INTEGRATION
1. Complete GitHub Actions Workflow
yaml# .github/workflows/ci-cd.yml

name: CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]
  release:
    types: [created]

env:
  PYTHON_VERSION: '3.11'
  POETRY_VERSION: '1.7.0'

jobs:
  # ============================================
  # CODE QUALITY
  # ============================================
  
  quality:
    name: Code Quality
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Full history for better analysis
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: 'pip'
      
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements-dev.txt
      
      - name: Cache pre-commit
        uses: actions/cache@v3
        with:
          path: ~/.cache/pre-commit
          key: pre-commit-${{ hashFiles('.pre-commit-config.yaml') }}
      
      - name: Run pre-commit
        run: pre-commit run --all-files --show-diff-on-failure
      
      - name: Upload pre-commit results
        if: failure()
        uses: actions/upload-artifact@v3
        with:
          name: pre-commit-results
          path: .git/pre-commit-output.txt


  # ============================================
  # LINTING
  # ============================================
  
  lint:
    name: Linting
    runs-on: ubuntu-latest
    
    strategy:
      matrix:
        linter: [ruff, flake8, pylint]
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
      
      - name: Install dependencies
        run: |
          pip install ${{ matrix.linter }}
          pip install -r requirements.txt
      
      - name: Run ${{ matrix.linter }}
        run: |
          if [ "${{ matrix.linter }}" == "ruff" ]; then
            ruff check . --output-format=github
          elif [ "${{ matrix.linter }}" == "flake8" ]; then
            flake8 . --format=github
          else
            pylint models services api --output-format=colorized
          fi


  # ============================================
  # TYPE CHECKING
  # ============================================
  
  type-check:
    name: Type Checking
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
      
      - name: Install dependencies
        run: |
          pip install mypy
          pip install -r requirements.txt
          pip install types-redis types-requests types-PyYAML
      
      - name: Run mypy
        run: mypy . --html-report ./mypy-report
      
      - name: Upload mypy report
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: mypy-report
          path: mypy-report/


  # ============================================
  # TESTING
  # ============================================
  
  test:
    name: Tests
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: test_db
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432
      
      redis:
        image: redis:7-alpine
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 6379:6379
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-test.txt
      
      - name: Run tests
        env:
          DATABASE_URL: postgresql://postgres:postgres@localhost:5432/test_db
          REDIS_HOST: localhost
          REDIS_PORT: 6379
        run: |
          pytest \
            --cov=. \
            --cov-report=xml \
            --cov-report=html \
            --cov-report=term \
            --junitxml=junit.xml \
            -v
      
      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v3
        with:
          files: ./coverage.xml
          flags: unittests
          name: codecov-umbrella
      
      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: test-results
          path: |
            junit.xml
            htmlcov/


  # ============================================
  # SECURITY
  # ============================================
  
  security:
    name: Security Scan
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
      
      - name: Install dependencies
        run: |
          pip install bandit safety
          pip install -r requirements.txt
      
      - name: Run Bandit
        run: bandit -r . -f json -o bandit-report.json
      
      - name: Run Safety
        run: safety check --json --output safety-report.json
      
      - name: Upload security reports
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: security-reports
          path: |
            bandit-report.json
            safety-report.json


  # ============================================
  # BUILD DOCKER IMAGE
  # ============================================
  
  build:
    name: Build Docker Image
    runs-on: ubuntu-latest
    needs: [quality, lint, type-check, test, security]
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      
      - name: Login to DockerHub
        if: github.event_name != 'pull_request'
        uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}
      
      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: yourorg/ocr-system
          tags: |
            type=ref,event=branch
            type=ref,event=pr
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
            type=sha
      
      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          push: ${{ github.event_name != 'pull_request' }}
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max


  # ============================================
  # DEPLOY
  # ============================================
  
  deploy:
    name: Deploy
    runs-on: ubuntu-latest
    needs: [build]
    if: github.ref == 'refs/heads/main'
    
    environment:
      name: production
      url: https://api.example.com
    
    steps:
      - name: Deploy to production
        run: |
          echo "Deploying to production..."
          # Add your deployment commands here

📦 COMPLETE SETUP GUIDE
1. Project Initialization Script
bash# scripts/init_project.sh

#!/bin/bash
# ============================================
# PROJECT INITIALIZATION SCRIPT
# ============================================

set -e

echo "🚀 Initializing OCR Processing Project"
echo "=" * 60
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# ============================================
# CHECK PREREQUISITES
# ============================================

echo "Checking prerequisites..."

# Python version
PYTHON_VERSION=$(python --version 2>&1 | awk '{print $2}')
echo "  Python version: $PYTHON_VERSION"

# Git
if ! command -v git &> /dev/null; then
    echo "  ✗ Git not found. Please install Git."
    exit 1
fi
echo "  ✓ Git found"

# Docker
if ! command -v docker &> /dev/null; then
    echo "  ⚠ Docker not found. Docker is optional but recommended."
else
    echo "  ✓ Docker found"
fi

echo ""

# ============================================
# CREATE VIRTUAL ENVIRONMENT
# ============================================

echo "Creating virtual environment..."

if [ ! -d "venv" ]; then
    python -m venv venv
    echo "  ✓ Virtual environment created"
else
    echo "  ⚠ Virtual environment already exists"
fi

# Activate virtual environment
source venv/bin/activate

echo ""

# ============================================
# INSTALL DEPENDENCIES
# ============================================

echo "Installing dependencies..."

pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt

echo "  ✓ Dependencies installed"
echo ""

# ============================================
# SETUP PRE-COMMIT
# ============================================

echo "Setting up pre-commit hooks..."

pre-commit install
pre-commit install --hook-type commit-msg

echo "  ✓ Pre-commit hooks installed"
echo ""

# ============================================
# CONFIGURE ENVIRONMENT
# ============================================

echo "Configuring environment..."

if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "  ✓ Created .env file"
    echo "  ⚠ Please edit .env with your settings"
else
    echo "  ⚠ .env file already exists"
fi

echo ""

# ============================================
# SETUP DATABASE
# ============================================

echo "Setting up database..."

# Check if PostgreSQL is running
if docker ps | grep -q postgres; then
    echo "  ✓ PostgreSQL container running"
    
    # Run migrations
    alembic upgrade head
    echo "  ✓ Database migrations applied"
else
    echo "  ⚠ PostgreSQL not running"
    echo "  Start with: docker-compose up -d postgres"
fi

echo ""

# ============================================
# RUN QUALITY CHECKS
# ============================================

echo "Running initial quality checks..."

# Format code
black .
isort .
echo "  ✓ Code formatted"

# Run linters
ruff check . --fix
echo "  ✓ Linters passed"

echo ""

# ============================================
# SUMMARY
# ============================================

echo -e "${GREEN}✓ Project initialization complete!${NC}"
echo ""
echo "Next steps:"
echo "  1. Edit .env with your configuration"
echo "  2. Start services: docker-compose up -d"
echo "  3. Run tests: pytest"
echo "  4. Start development: uvicorn main:app --reload"
echo ""
echo "Documentation:"
echo "  - API docs: http://localhost:8000/docs"
echo "  - README: ./README.md"
echo "  - Contributing: ./CONTRIBUTING.md"
echo ""
2. Development Setup Checklist
markdown# DEVELOPMENT_SETUP.md

# Development Setup Checklist

## Prerequisites

- [ ] Python 3.11+ installed
- [ ] Git installed
- [ ] Docker installed (optional)
- [ ] PostgreSQL 15+ (or use Docker)
- [ ] Redis 7+ (or use Docker)
- [ ] NVIDIA GPU with CUDA 11.8+ (optional, for GPU backends)

## Initial Setup

### 1. Clone Repository
```bash
git clone https://github.com/yourorg/ocr-system.git
cd ocr-system
```

### 2. Run Init Script
```bash
chmod +x scripts/init_project.sh
./scripts/init_project.sh
```

### 3. Manual Configuration

Edit `.env` file:
```bash
# Required
DATABASE_URL=postgresql://user:pass@localhost:5432/ocr_db
REDIS_HOST=localhost
SECRET_KEY=generate-a-secure-key-here

# Optional
OCR_GPU_ENABLED=true
DEBUG=true
```

Generate secure secret key:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 4. Start Services

**Option A: Docker Compose**
```bash
docker-compose up -d
```

**Option B: Manual**
```bash
# PostgreSQL
sudo systemctl start postgresql

# Redis
sudo systemctl start redis

# Application
uvicorn main:app --reload
```

### 5. Verify Setup
```bash
# Check health endpoint
curl http://localhost:8000/health

# Run tests
pytest

# Check code quality
make quality-check
```

## IDE Setup

### VS Code

Install recommended extensions:
- Python
- Pylance
- Black Formatter
- isort
- GitLens
- Docker

Settings (`.vscode/settings.json`):
```json
{
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": true,
  "python.linting.flake8Enabled": true,
  "python.formatting.provider": "black",
  "editor.formatOnSave": true,
  "python.linting.mypyEnabled": true
}
```

### PyCharm

1. Open project
2. Configure Python interpreter (venv)
3. Enable:
   - Code inspections
   - PEP 8 checking
   - Type checking

## Development Workflow

### Daily Workflow
```bash
# Start day
git pull origin develop
docker-compose up -d

# Make changes
# ...

# Before commit
make quality-check
pytest

# Commit
git add .
git commit -m "feat: add feature"

# Push
git push origin feature/my-feature
```

### Code Quality Commands
```bash
# Format code
make format

# Run linters
make lint

# Type checking
make type-check

# All checks
make quality-check

# Fix auto-fixable issues
make fix
```

## Troubleshooting

### Common Issues

**Issue**: Pre-commit hooks fail
```bash
# Update hooks
pre-commit autoupdate

# Re-run
pre-commit run --all-files
```

**Issue**: Database connection error
```bash
# Check PostgreSQL
docker ps | grep postgres

# Check logs
docker-compose logs postgres

# Restart
docker-compose restart postgres
```

**Issue**: Import errors
```bash
# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

## Resources

- [Contributing Guidelines](CONTRIBUTING.md)
- [Code Review Guidelines](docs/CODE_REVIEW.md)
- [API Documentation](http://localhost:8000/docs)
- [Architecture](docs/ARCHITECTURE.md)

✅ BEST PRACTICES SUMMARY
python# best_practices_summary.py

"""
Code Quality Best Practices Summary

Quick reference for development standards
"""

BEST_PRACTICES = {
    # ============================================
    # STYLE
    # ============================================
    "style": {
        "DO": [
            "Follow PEP 8 strictly",
            "Use 4 spaces for indentation",
            "Keep lines under 100 characters",
            "Use snake_case for functions/variables",
            "Use PascalCase for classes",
            "Use UPPERCASE for constants",
            "Add docstrings to all public APIs",
            "Use meaningful variable names",
        ],
        "DON'T": [
            "Use tabs for indentation",
            "Mix naming conventions",
            "Use single-letter variables (except i, j, k)",
            "Leave commented-out code",
            "Use wildcard imports (from x import *)",
            "Write functions longer than 50 lines",
        ],
    },
    
    # ============================================
    # TYPE HINTS
    # ============================================
    "type_hints": {
        "DO": [
            "Add type hints to all functions",
            "Use Optional for nullable values",
            "Use TypedDict for dict structures",
            "Use Protocol for structural typing",
            "Run mypy regularly",
            "Add return type hints",
        ],
        "DON'T": [
            "Skip type hints",
            "Use Any excessively",
            "Ignore mypy warnings",
            "Use type: ignore without explanation",
        ],
    },
    
    # ============================================
    # LINTING
    # ============================================
    "linting": {
        "DO": [
            "Run linters before committing",
            "Fix all linter warnings",
            "Use auto-fix when available",
            "Configure linters in pyproject.toml",
            "Use Ruff for speed",
        ],
        "DON'T": [
            "Ignore linter warnings",
            "Disable rules without reason",
            "Skip linting in CI/CD",
        ],
    },
    
    # ============================================
    # FORMATTING
    # ============================================
    "formatting": {
        "DO": [
            "Use Black for formatting",
            "Use isort for imports",
            "Format before committing",
            "Configure editor to format on save",
        ],
        "DON'T": [
            "Format manually",
            "Skip formatting checks",
            "Override Black configuration unnecessarily",
        ],
    },
    
    # ============================================
    # DOCUMENTATION
    # ============================================
    "documentation": {
        "DO": [
            "Write docstrings for all public APIs",
            "Include examples in docstrings",
            "Document complex logic",
            "Keep README up to date",
            "Document breaking changes",
            "Use Google-style docstrings",
        ],
        "DON'T": [
            "Write obvious comments",
            "Leave TODOs without issues",
            "Skip API documentation",
            "Forget to update docs when changing code",
        ],
    },
    
    # ============================================
    # TESTING
    # ============================================
    "testing": {
        "DO": [
            "Write tests for new code",
            "Aim for >80% coverage",
            "Test edge cases",
            "Use fixtures for setup",
            "Name tests descriptively",
            "Follow AAA pattern (Arrange, Act, Assert)",
        ],
        "DON'T": [
            "Skip tests",
            "Test implementation details",
            "Write flaky tests",
            "Ignore failing tests",
        ],
    },
    
    # ============================================
    # GIT
    # ============================================
    "git": {
        "DO": [
            "Write clear commit messages",
            "Make atomic commits",
            "Use conventional commits format",
            "Create feature branches",
            "Rebase before merging",
            "Squash small commits",
        ],
        "DON'T": [
            "Commit directly to main",
            "Write vague commit messages",
            "Commit broken code",
            "Include secrets in commits",
            "Force push to shared branches",
        ],
    },
    
    # ============================================
    # CODE REVIEW
    # ============================================
    "code_review": {
        "DO": [
            "Review thoroughly",
            "Be constructive",
            "Suggest alternatives",
            "Test changes locally",
            "Check documentation",
            "Approve explicitly",
        ],
        "DON'T": [
            "Rubber-stamp reviews",
            "Be dismissive",
            "Focus only on style",
            "Ignore security issues",
        ],
    },
    
    # ============================================
    # SECURITY
    # ============================================
    "security": {
        "DO": [
            "Validate all inputs",
            "Use parameterized queries",
            "Encrypt sensitive data",
            "Use environment variables for secrets",
            "Run security scanners",
            "Keep dependencies updated",
        ],
        "DON'T": [
            "Commit secrets",
            "Trust user input",
            "Use eval() or exec()",
            "Disable security features",
            "Ignore security warnings",
        ],
    },
}


# Print summary
def print_best_practices():
    """Print best practices summary"""
    for category, practices in BEST_PRACTICES.items():
        print(f"\n{'='*60}")
        print(f"{category.upper()}")
        print('='*60)
        
        print("\n✓ DO:")
        for item in practices["DO"]:
            print(f"  • {item}")
        
        print("\n✗ DON'T:")
        for item in practices["DON'T"]:
            print(f"  • {item}")


if __name__ == "__main__":
    print_best_practices()
```

---

## 🎯 FINAL SUMMARY
```
┌──────────────────────────────────────────────────────────────┐
│     COMPLETE CODE QUALITY & STANDARDS COVERAGE               │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ✅ Python Style Guide (PEP 8)                               │
│     - Complete examples and patterns                         │
│     - Project-specific conventions                           │
│     - Naming standards                                       │
│                                                              │
│  ✅ Type Hints & mypy                                        │
│     - Comprehensive typing guide                             │
│     - Advanced patterns (Generics, Protocols)                │
│     - Complete configuration                                 │
│                                                              │
│  ✅ Linting (Ruff, Flake8, Pylint)                           │
│     - All major linters configured                           │
│     - Integration scripts                                    │
│     - CI/CD ready                                            │
│                                                              │
│  ✅ Formatting (Black & isort)                               │
│     - Complete setup                                         │
│     - Before/after examples                                  │
│     - Automation scripts                                     │
│                                                              │
│  ✅ Pre-commit Hooks                                         │
│     - 15+ configured hooks                                   │
│     - Custom hooks                                           │
│     - GitHub Actions integration                             │
│                                                              │
│  ✅ Code Review Guidelines                                   │
│     - Comprehensive checklists                               │
│     - Comment templates                                      │
│     - PR templates                                           │
│                                                              │
│  ✅ Documentation Standards                                  │
│     - Docstring examples (all types)                         │
│     - API documentation setup                                │
│     - README template                                        │
│                                                              │
│  ✅ CI/CD Integration                                        │
│     - Complete GitHub Actions workflow                       │
│     - Multi-stage pipeline                                   │
│     - Security scanning                                      │
│                                                              │
│  ✅ Complete Setup Guide                                     │
│     - Initialization script                                  │
│     - Development checklist                                  │
│     - Troubleshooting guide                                  │
│                                                              │
│  ✅ Best Practices Summary                                   │
│     - Quick reference                                        │
│     - Do's and Don'ts                                        │
│     - All categories covered                                 │
│                                                              │
└──────────────────────────────────────────────────────────────┘