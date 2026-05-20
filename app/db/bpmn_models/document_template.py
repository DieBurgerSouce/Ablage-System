"""
Document Template Models

Re-exports canonical models from app.db.models_template_knowledge to avoid
duplicate __tablename__ definitions that crash SQLAlchemy at startup.

Original document template models are defined in:
    app/db/models_template_knowledge.py
"""

# Import all template-related models and enums from the canonical source
from app.db.models_template_knowledge import (  # noqa: F401
    DocumentTemplate,
    GeneratedDocument,
    TemplateCategory,
    TemplateOutputFormat,
    TemplateSnippet,
    VariableType,
)
