"""Banking-Unit-Test-Fixtures.

Die Multi-Tenant-Tests (test_multi_tenant_migration.py) fordern eine
``db``-Fixture; tests/conftest.py stellt nur ``test_db`` bereit. Dieser
Alias macht die 17 Tests lauffähig, ohne alle Signaturen umzubenennen.
Ohne erreichbares PostgreSQL skippt ``test_db`` sauber.
"""

from collections.abc import AsyncGenerator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def db(test_db: AsyncSession) -> AsyncGenerator[AsyncSession, None]:
    """Alias auf die Session-Fixture ``test_db`` aus tests/conftest.py."""
    yield test_db
