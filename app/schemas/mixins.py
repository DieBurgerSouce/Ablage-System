"""Pydantic Schema Mixins fuer Optimistic Locking.

Stellt Basis-Mixins bereit, die in Response- und Update-Schemas
eingebunden werden koennen, um row_version konsistent zu transportieren.

Verwendung in Response-Schemas:
    class DocumentResponse(RowVersionMixin):
        id: UUID
        filename: str
        ...

Verwendung in Update-Schemas:
    class DocumentUpdate(RowVersionRequiredMixin):
        filename: Optional[str] = None
        ...
"""

from pydantic import BaseModel, Field


class RowVersionMixin(BaseModel):
    """Mixin fuer Schemas die row_version enthalten.

    Fuer Response-Schemas: row_version wird mit default=1
    zurueckgegeben, falls noch nie ein UPDATE erfolgte.
    """

    row_version: int = Field(
        default=1,
        description=(
            "Version fuer Optimistic Locking. "
            "Muss bei Updates mitgesendet werden."
        ),
        ge=1,
    )


class RowVersionRequiredMixin(BaseModel):
    """Mixin fuer Update-Schemas die row_version ERFORDERN.

    Der Client muss die aktuelle row_version mitsenden.
    Bei Konflikt (anderer Nutzer hat zwischenzeitlich geaendert)
    gibt die API HTTP 409 Conflict zurueck.
    """

    row_version: int = Field(
        ...,
        description=(
            "Aktuelle Version des Objekts. "
            "Bei Konflikt wird HTTP 409 zurueckgegeben."
        ),
        ge=1,
    )
