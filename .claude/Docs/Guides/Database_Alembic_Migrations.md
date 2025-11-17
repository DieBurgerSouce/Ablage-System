🔄 ALEMBIC MIGRATIONS - COMPLETE GUIDE
Schema Evolution Management für SQLAlchemy Models

📋 TABLE OF CONTENTS

Introduction
Installation & Setup
Configuration
Creating Migrations
Running Migrations
Rollback & Downgrade
Auto-Generation
Data Migrations
Branching & Merging
Best Practices
Production Workflow
Common Scenarios
Troubleshooting


🎯 INTRODUCTION
What is Alembic?
Alembic is a lightweight database migration tool for SQLAlchemy. It allows you to:

Track schema changes over time
Version control your database structure
Apply changes incrementally across environments
Rollback changes if needed
Auto-generate migrations from model changes
Manage data transformations during schema changes

Why Use Migrations?
❌ WITHOUT MIGRATIONS:
- Manual SQL scripts
- No version control
- Difficult to sync across environments
- Risky production deployments
- Hard to rollback

✅ WITH MIGRATIONS:
- Automated schema updates
- Version controlled changes
- Consistent across dev/staging/prod
- Safe rollback mechanism
- Easy team collaboration

📦 INSTALLATION & SETUP
1. Install Alembic
bash# Install Alembic
pip install alembic

# Or add to requirements.txt
echo "alembic==1.13.1" >> requirements.txt
pip install -r requirements.txt
2. Initialize Alembic
bash# In your project root (where backend/ is)
cd backend
alembic init alembic

# This creates:
# ├── alembic/
# │   ├── env.py              # Migration environment
# │   ├── script.py.mako      # Migration template
# │   └── versions/           # Migration files go here
# └── alembic.ini             # Configuration file
```

### 3. Project Structure
```
backend/
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       ├── 001_initial_schema.py
│       ├── 002_add_document_tags.py
│       └── 003_add_webhooks.py
├── models/
│   ├── __init__.py
│   ├── auth.py
│   ├── documents.py
│   └── ...
├── alembic.ini
├── database.py
└── requirements.txt

⚙️ CONFIGURATION
1. Configure alembic.ini
ini# alembic.ini

[alembic]
# Path to migration scripts
script_location = alembic

# Template used to generate migration files
file_template = %%(year)d%%(month).2d%%(day).2d_%%(hour).2d%%(minute).2d_%%(slug)s

# Timezone for timestamps
timezone = UTC

# Version location specification
version_locations = alembic/versions

# Prepend sys.path with this value (for imports)
prepend_sys_path = .

# Database URL (can be overridden by env.py)
# DO NOT put real credentials here - use env.py instead
sqlalchemy.url = postgresql://user:pass@localhost/dbname

# Logging configuration
[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
2. Configure env.py
python# alembic/env.py

from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Import your models' Base
from database import Base
from models import *  # Import all models to register them

# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set target metadata
target_metadata = Base.metadata

# Get database URL from environment variable (for security)
def get_url():
    # Option 1: From environment variable
    db_url = os.getenv('DATABASE_URL')
    
    # Option 2: From database.py configuration
    if not db_url:
        from database import SQLALCHEMY_DATABASE_URL
        db_url = SQLALCHEMY_DATABASE_URL
    
    return db_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well. By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,  # Compare column types
        compare_server_default=True,  # Compare server defaults
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    # Override sqlalchemy.url with dynamic URL
    configuration = config.get_section(config.config_ini_section)
    configuration['sqlalchemy.url'] = get_url()
    
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,  # Detect type changes
            compare_server_default=True,  # Detect default value changes
            include_schemas=False,  # Don't include schema name in table names
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
3. Environment Variables
bash# .env
DATABASE_URL=postgresql://user:password@localhost:5432/ocr_db

# For production
DATABASE_URL=postgresql://prod_user:secure_pass@prod-server:5432/ocr_prod

🔨 CREATING MIGRATIONS
1. Empty Migration (Manual)
bash# Create empty migration file
alembic revision -m "add_document_tags"

# Creates: versions/20250116_1430_add_document_tags.py
Manual Migration Example:
python# versions/20250116_1430_add_document_tags.py

"""add document tags

Revision ID: abc123def456
Revises: previous_revision
Create Date: 2025-01-16 14:30:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'abc123def456'
down_revision = 'previous_revision'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade schema"""
    # Add tags column to documents table
    op.add_column(
        'documents',
        sa.Column('tags', postgresql.ARRAY(sa.String()), nullable=True)
    )
    
    # Create index on tags
    op.create_index(
        'idx_documents_tags',
        'documents',
        ['tags'],
        postgresql_using='gin'
    )


def downgrade() -> None:
    """Downgrade schema"""
    # Remove index
    op.drop_index('idx_documents_tags', table_name='documents')
    
    # Remove column
    op.drop_column('documents', 'tags')
2. Auto-Generate Migration
bash# Generate migration from model changes
alembic revision --autogenerate -m "add_webhooks_table"

# Alembic compares models with database and generates migration
Auto-Generated Example:
python# versions/20250116_1445_add_webhooks_table.py

"""add webhooks table

Revision ID: def456ghi789
Revises: abc123def456
Create Date: 2025-01-16 14:45:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'def456ghi789'
down_revision = 'abc123def456'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Auto-generated
    op.create_table(
        'webhooks',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('events', postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column('secret', sa.String(length=255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_webhooks_user_id'), 'webhooks', ['user_id'], unique=False)
    op.create_index(op.f('ix_webhooks_is_active'), 'webhooks', ['is_active'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_webhooks_is_active'), table_name='webhooks')
    op.drop_index(op.f('ix_webhooks_user_id'), table_name='webhooks')
    op.drop_table('webhooks')
3. Create Initial Migration
bash# First time setup - create migration from all models
alembic revision --autogenerate -m "initial_schema"

# This creates the complete database schema

▶️ RUNNING MIGRATIONS
1. Basic Commands
bash# Upgrade to latest version (head)
alembic upgrade head

# Upgrade by one version
alembic upgrade +1

# Upgrade to specific revision
alembic upgrade abc123def456

# Show current version
alembic current

# Show migration history
alembic history

# Show migration history with details
alembic history --verbose
2. Step-by-Step Upgrade
bash# Check current version
alembic current
# Current revision: abc123def456

# View pending migrations
alembic history -r current:head
# abc123def456 -> def456ghi789 (head), add webhooks table

# Upgrade by one migration
alembic upgrade +1

# Verify
alembic current
# Current revision: def456ghi789
3. Dry Run (Show SQL)
bash# Show SQL without executing
alembic upgrade head --sql

# Output SQL to file
alembic upgrade head --sql > migration.sql

⏪ ROLLBACK & DOWNGRADE
1. Downgrade Commands
bash# Downgrade by one version
alembic downgrade -1

# Downgrade to specific revision
alembic downgrade abc123def456

# Downgrade to base (empty database)
alembic downgrade base

# DANGER: This removes ALL tables!
2. Safe Rollback Pattern
bash# 1. Check current version
alembic current

# 2. View what will be rolled back
alembic history -r current-1:current

# 3. Backup database first!
pg_dump ocr_db > backup_before_rollback.sql

# 4. Downgrade
alembic downgrade -1

# 5. Verify
alembic current
3. Recover from Failed Migration
bash# If migration fails mid-way:

# Option 1: Force stamp to working version
alembic stamp abc123def456

# Option 2: Edit migration and retry
alembic upgrade head

# Option 3: Rollback and fix
alembic downgrade -1
# Edit migration file
alembic upgrade head

🤖 AUTO-GENERATION
1. How Auto-Generation Works
python# Alembic compares:
1. SQLAlchemy models (what SHOULD be)
2. Current database (what IS)
3. Generates migration for differences
2. What Auto-Generates
✅ Auto-Detected:

New tables
Removed tables
New columns
Removed columns
Column type changes
Nullable changes
Index changes
Foreign key changes
Primary key changes

⚠️ NOT Auto-Detected:

Table/column renames (seen as drop + create)
Check constraints
Enum changes
Some complex types

3. Review Auto-Generated Migrations
bash# ALWAYS review auto-generated migrations!
alembic revision --autogenerate -m "changes"

# Check the generated file
cat alembic/versions/20250116_1500_changes.py
Example Review:
python# BAD - Column rename detected as drop + create
def upgrade():
    op.drop_column('documents', 'old_name')
    op.add_column('documents', sa.Column('new_name', sa.String(), nullable=True))
    
# GOOD - Edit to preserve data
def upgrade():
    op.alter_column('documents', 'old_name', new_column_name='new_name')
4. Exclude Tables from Auto-Generation
python# alembic/env.py

def run_migrations_online():
    # Exclude specific tables
    def include_object(object, name, type_, reflected, compare_to):
        # Don't auto-generate migrations for temporary tables
        if type_ == "table" and name.startswith("temp_"):
            return False
        return True
    
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,  # Add this
        compare_type=True,
    )

💾 DATA MIGRATIONS
1. Migrate Existing Data
python# versions/20250116_1600_migrate_user_roles.py

"""migrate user roles to new system

Revision ID: ghi789jkl012
Revises: def456ghi789
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column

revision = 'ghi789jkl012'
down_revision = 'def456ghi789'


def upgrade() -> None:
    # Create new roles table
    op.create_table(
        'roles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(50), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Define table for data migration
    roles = table(
        'roles',
        column('id', sa.Integer),
        column('name', sa.String)
    )
    
    # Insert default roles
    op.bulk_insert(roles, [
        {'id': 1, 'name': 'admin'},
        {'id': 2, 'name': 'user'},
        {'id': 3, 'name': 'reviewer'}
    ])
    
    # Add role_id column to users
    op.add_column('users', sa.Column('role_id', sa.Integer(), nullable=True))
    
    # Migrate existing users to 'user' role
    op.execute("UPDATE users SET role_id = 2 WHERE role_id IS NULL")
    
    # Make role_id non-nullable
    op.alter_column('users', 'role_id', nullable=False)
    
    # Add foreign key
    op.create_foreign_key(
        'fk_users_role_id',
        'users', 'roles',
        ['role_id'], ['id']
    )


def downgrade() -> None:
    op.drop_constraint('fk_users_role_id', 'users', type_='foreignkey')
    op.drop_column('users', 'role_id')
    op.drop_table('roles')
2. Transform Data During Migration
python# versions/20250116_1700_normalize_email_addresses.py

"""normalize email addresses to lowercase

Revision ID: jkl012mno345
Revises: ghi789jkl012
"""
from alembic import op

revision = 'jkl012mno345'
down_revision = 'ghi789jkl012'


def upgrade() -> None:
    # Normalize all email addresses to lowercase
    op.execute("""
        UPDATE users 
        SET email = LOWER(email)
        WHERE email != LOWER(email)
    """)
    
    # Add check constraint to enforce lowercase
    op.create_check_constraint(
        'ck_users_email_lowercase',
        'users',
        'email = LOWER(email)'
    )


def downgrade() -> None:
    op.drop_constraint('ck_users_email_lowercase', 'users', type_='check')
    # Note: Can't reverse the lowercase transformation
3. Complex Data Migration
python# versions/20250116_1800_split_name_column.py

"""split full_name into first_name and last_name

Revision ID: mno345pqr678
Revises: jkl012mno345
"""
from alembic import op
import sqlalchemy as sa

revision = 'mno345pqr678'
down_revision = 'jkl012mno345'


def upgrade() -> None:
    # Add new columns
    op.add_column('users', sa.Column('first_name', sa.String(100), nullable=True))
    op.add_column('users', sa.Column('last_name', sa.String(100), nullable=True))
    
    # Split existing full_name data
    op.execute("""
        UPDATE users
        SET 
            first_name = SPLIT_PART(full_name, ' ', 1),
            last_name = CASE 
                WHEN full_name LIKE '% %' 
                THEN SUBSTRING(full_name FROM POSITION(' ' IN full_name) + 1)
                ELSE ''
            END
        WHERE full_name IS NOT NULL
    """)
    
    # Make columns non-nullable
    op.alter_column('users', 'first_name', nullable=False)
    op.alter_column('users', 'last_name', nullable=False)
    
    # Remove old column
    op.drop_column('users', 'full_name')


def downgrade() -> None:
    # Add back full_name column
    op.add_column('users', sa.Column('full_name', sa.String(200), nullable=True))
    
    # Reconstruct full_name
    op.execute("""
        UPDATE users
        SET full_name = first_name || ' ' || last_name
    """)
    
    op.alter_column('users', 'full_name', nullable=False)
    
    # Remove split columns
    op.drop_column('users', 'last_name')
    op.drop_column('users', 'first_name')

🌿 BRANCHING & MERGING
1. Create Branch
bash# Create development branch
alembic revision -m "dev_feature" --head=def456ghi789 --branch-label=dev

# Create production branch
alembic revision -m "prod_hotfix" --head=def456ghi789 --branch-label=prod
2. View Branches
bash# Show current branches
alembic branches

# Show detailed branch history
alembic history --verbose
3. Merge Branches
bash# Create merge migration
alembic merge -m "merge_dev_and_prod" heads

# This creates a migration with two down_revisions
Merge Migration Example:
python# versions/20250116_1900_merge_dev_and_prod.py

"""merge dev and prod branches

Revision ID: pqr678stu901
Revises: abc123xyz789, def456uvw012
"""

revision = 'pqr678stu901'
down_revision = ('abc123xyz789', 'def456uvw012')  # Two parents!
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Usually empty - branches already applied separately
    pass


def downgrade() -> None:
    pass

✅ BEST PRACTICES
1. Migration File Naming
bash# GOOD naming
alembic revision -m "add_document_tags"
alembic revision -m "remove_legacy_status_column"
alembic revision -m "create_webhooks_table"

# BAD naming
alembic revision -m "changes"
alembic revision -m "update"
alembic revision -m "fix"
2. Write Reversible Migrations
python# ALWAYS implement both upgrade() and downgrade()

def upgrade() -> None:
    op.add_column('documents', sa.Column('tags', ARRAY(String)))

def downgrade() -> None:
    op.drop_column('documents', 'tags')  # Must be reversible!
3. Test Migrations
bash# Test upgrade
alembic upgrade head

# Test downgrade
alembic downgrade -1

# Test re-upgrade
alembic upgrade head
4. Backup Before Migrations
bash# ALWAYS backup production before migrating!

# PostgreSQL
pg_dump -Fc ocr_db > backup_$(date +%Y%m%d_%H%M%S).dump

# Restore if needed
pg_restore -d ocr_db backup_20250116_143000.dump
5. Small, Focused Migrations
python# GOOD - One logical change
# Migration 1: Add column
def upgrade():
    op.add_column('users', sa.Column('phone', sa.String(20)))

# Migration 2: Populate data
def upgrade():
    op.execute("UPDATE users SET phone = '000-000-0000' WHERE phone IS NULL")

# BAD - Too many changes
def upgrade():
    op.add_column('users', sa.Column('phone', sa.String(20)))
    op.add_column('users', sa.Column('address', sa.Text()))
    op.create_table('user_preferences', ...)
    op.execute("UPDATE ...")  # Don't mix schema + data!
6. Review Auto-Generated Migrations
python# Auto-generated migrations need review!

# Generated (might be wrong):
def upgrade():
    op.drop_column('users', 'name')
    op.add_column('users', sa.Column('full_name', sa.String()))

# Should be (preserves data):
def upgrade():
    op.alter_column('users', 'name', new_column_name='full_name')
7. Handle Nullable Properly
python# GOOD - Add nullable first, then make non-nullable
def upgrade():
    # Step 1: Add nullable column
    op.add_column('users', sa.Column('email', sa.String(), nullable=True))
    
    # Step 2: Populate data
    op.execute("UPDATE users SET email = username || '@example.com'")
    
    # Step 3: Make non-nullable
    op.alter_column('users', 'email', nullable=False)

# BAD - Add non-nullable directly (fails if table has data!)
def upgrade():
    op.add_column('users', sa.Column('email', sa.String(), nullable=False))
8. Document Complex Migrations
python"""migrate user authentication system

This migration:
1. Creates new 'auth_providers' table
2. Migrates existing password hashes
3. Updates foreign key relationships
4. Removes legacy 'password' column

Data migration strategy:
- All existing users get 'local' auth provider
- Password hashes moved to auth_providers.credentials
- Email remains primary identifier

Rollback considerations:
- Downgrade recreates password column
- Auth provider data is lost on rollback
"""

🚀 PRODUCTION WORKFLOW
1. Development Workflow
bash# 1. Make model changes
# Edit models/documents.py

# 2. Generate migration
alembic revision --autogenerate -m "add_document_status"

# 3. Review generated migration
cat alembic/versions/latest_migration.py

# 4. Edit if needed
vim alembic/versions/latest_migration.py

# 5. Test locally
alembic upgrade head
alembic downgrade -1
alembic upgrade head

# 6. Commit to git
git add alembic/versions/latest_migration.py models/documents.py
git commit -m "Add document status field"
git push
2. Staging Deployment
bash# 1. Pull latest code
git pull origin main

# 2. Backup database
pg_dump staging_db > staging_backup_$(date +%Y%m%d).dump

# 3. Check current version
alembic current

# 4. Show pending migrations
alembic history -r current:head

# 5. Run migrations
alembic upgrade head

# 6. Verify
alembic current
3. Production Deployment
bash# CRITICAL: Follow this process exactly!

# 1. Maintenance mode ON
# (Application should queue requests)

# 2. Full database backup
pg_dump -Fc production_db > prod_backup_$(date +%Y%m%d_%H%M%S).dump

# 3. Verify backup
pg_restore --list prod_backup_20250116_143000.dump | head

# 4. Check current version
alembic -c production.ini current

# 5. Dry run (show SQL)
alembic -c production.ini upgrade head --sql > migration.sql

# 6. Review SQL
less migration.sql

# 7. Run migration with logging
alembic -c production.ini upgrade head 2>&1 | tee migration.log

# 8. Verify success
alembic -c production.ini current

# 9. Quick smoke test
# (Test critical application features)

# 10. Maintenance mode OFF

# If something went wrong:
# alembic -c production.ini downgrade -1
# pg_restore -d production_db prod_backup_20250116_143000.dump
4. Zero-Downtime Migrations
python# Phase 1: Add new column (nullable)
def upgrade():
    op.add_column('users', sa.Column('new_email', sa.String(), nullable=True))

# Deploy application code that writes to BOTH columns

# Phase 2: Backfill data
def upgrade():
    op.execute("UPDATE users SET new_email = email WHERE new_email IS NULL")

# Phase 3: Make non-nullable and switch
def upgrade():
    op.alter_column('users', 'new_email', nullable=False)
    op.create_index('idx_users_new_email', 'users', ['new_email'])

# Deploy application code that uses new_email

# Phase 4: Remove old column
def upgrade():
    op.drop_column('users', 'email')
    op.alter_column('users', 'new_email', new_column_name='email')

📚 COMMON SCENARIOS
Scenario 1: Add New Table
pythondef upgrade() -> None:
    op.create_table(
        'audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('details', postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index('idx_audit_logs_user_id', 'audit_logs', ['user_id'])
    op.create_index('idx_audit_logs_timestamp', 'audit_logs', ['timestamp'])

def downgrade() -> None:
    op.drop_index('idx_audit_logs_timestamp')
    op.drop_index('idx_audit_logs_user_id')
    op.drop_table('audit_logs')
Scenario 2: Add Column with Default
pythondef upgrade() -> None:
    # Add column with default value
    op.add_column(
        'documents',
        sa.Column('priority', sa.Integer(), server_default='0', nullable=False)
    )

def downgrade() -> None:
    op.drop_column('documents', 'priority')
Scenario 3: Change Column Type
pythondef upgrade() -> None:
    # Change column type (PostgreSQL specific)
    op.alter_column(
        'documents',
        'file_size',
        type_=sa.BigInteger(),
        existing_type=sa.Integer(),
        postgresql_using='file_size::bigint'  # Cast existing values
    )

def downgrade() -> None:
    op.alter_column(
        'documents',
        'file_size',
        type_=sa.Integer(),
        existing_type=sa.BigInteger(),
        postgresql_using='file_size::integer'
    )
Scenario 4: Add Foreign Key
pythondef upgrade() -> None:
    # Add foreign key
    op.create_foreign_key(
        'fk_documents_category_id',  # Constraint name
        'documents',  # Source table
        'categories',  # Target table
        ['category_id'],  # Source columns
        ['id'],  # Target columns
        ondelete='SET NULL'  # On delete action
    )

def downgrade() -> None:
    op.drop_constraint('fk_documents_category_id', 'documents', type_='foreignkey')
Scenario 5: Create Index
pythondef upgrade() -> None:
    # Simple index
    op.create_index('idx_documents_status', 'documents', ['status'])
    
    # Composite index
    op.create_index(
        'idx_documents_user_created',
        'documents',
        ['user_id', 'created_at']
    )
    
    # Partial index (PostgreSQL)
    op.create_index(
        'idx_documents_active',
        'documents',
        ['status'],
        postgresql_where=sa.text("status = 'active'")
    )
    
    # GIN index for JSONB (PostgreSQL)
    op.create_index(
        'idx_documents_metadata',
        'documents',
        ['metadata'],
        postgresql_using='gin'
    )

def downgrade() -> None:
    op.drop_index('idx_documents_metadata')
    op.drop_index('idx_documents_active')
    op.drop_index('idx_documents_user_created')
    op.drop_index('idx_documents_status')
Scenario 6: Add Enum Type
pythondef upgrade() -> None:
    # Create enum type
    document_status = postgresql.ENUM(
        'pending', 'processing', 'completed', 'failed',
        name='document_status_enum'
    )
    document_status.create(op.get_bind())
    
    # Add column using enum
    op.add_column(
        'documents',
        sa.Column('status', document_status, nullable=False, server_default='pending')
    )

def downgrade() -> None:
    op.drop_column('documents', 'status')
    
    # Drop enum type
    sa.Enum(name='document_status_enum').drop(op.get_bind())
Scenario 7: Rename Table
pythondef upgrade() -> None:
    op.rename_table('old_table_name', 'new_table_name')

def downgrade() -> None:
    op.rename_table('new_table_name', 'old_table_name')
Scenario 8: Add Check Constraint
pythondef upgrade() -> None:
    op.create_check_constraint(
        'ck_documents_file_size_positive',
        'documents',
        'file_size > 0'
    )

def downgrade() -> None:
    op.drop_constraint('ck_documents_file_size_positive', 'documents', type_='check')

🔧 TROUBLESHOOTING
Error: "Can't locate revision"
bash# Problem: Migration file is missing or revision IDs don't match

# Solution 1: Check if file exists
ls alembic/versions/

# Solution 2: Re-stamp database
alembic stamp head

# Solution 3: Edit alembic_version table directly
psql ocr_db
SELECT * FROM alembic_version;
UPDATE alembic_version SET version_num = 'correct_revision_id';
Error: "Table already exists"
bash# Problem: Database has tables but alembic thinks it's empty

# Solution: Stamp database to match current schema
alembic stamp head
Error: "Multiple heads in database"
bash# Problem: Multiple migration branches exist

# Solution: Create merge migration
alembic merge -m "merge_branches" heads
alembic upgrade head
Error: "Foreign key constraint fails"
python# Problem: Trying to add FK to column with invalid references

# Solution: Clean data first, then add constraint
def upgrade():
    # Step 1: Clean invalid references
    op.execute("""
        UPDATE documents 
        SET category_id = NULL 
        WHERE category_id NOT IN (SELECT id FROM categories)
    """)
    
    # Step 2: Add foreign key
    op.create_foreign_key(
        'fk_documents_category_id',
        'documents',
        'categories',
        ['category_id'],
        ['id']
    )
Error: "Column cannot be cast automatically"
python# Problem: PostgreSQL can't automatically convert types

# Solution: Specify cast with postgresql_using
def upgrade():
    op.alter_column(
        'documents',
        'created_at',
        type_=sa.DateTime(timezone=True),
        postgresql_using='created_at::timestamp with time zone'
    )
Error: "Duplicate key value violates unique constraint"
python# Problem: Adding unique constraint to column with duplicates

# Solution: Clean duplicates first
def upgrade():
    # Step 1: Remove duplicates
    op.execute("""
        DELETE FROM users
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM users
            GROUP BY email
        )
    """)
    
    # Step 2: Add unique constraint
    op.create_unique_constraint('uq_users_email', 'users', ['email'])

📝 QUICK REFERENCE
Essential Commands
bash# Initialize
alembic init alembic

# Create migration
alembic revision -m "description"
alembic revision --autogenerate -m "description"

# Upgrade
alembic upgrade head          # Latest
alembic upgrade +1            # One step
alembic upgrade abc123        # Specific revision

# Downgrade
alembic downgrade -1          # One step back
alembic downgrade abc123      # Specific revision
alembic downgrade base        # Remove all

# Information
alembic current               # Current version
alembic history               # Show history
alembic history --verbose     # Detailed history
alembic show abc123           # Show migration details

# Advanced
alembic stamp head            # Mark as up-to-date
alembic branches              # Show branches
alembic merge heads           # Merge branches
Common Operations
python# Add column
op.add_column('table', sa.Column('name', sa.String()))

# Drop column
op.drop_column('table', 'column_name')

# Rename column
op.alter_column('table', 'old_name', new_column_name='new_name')

# Change type
op.alter_column('table', 'column', type_=sa.Integer())

# Add index
op.create_index('idx_name', 'table', ['column'])

# Drop index
op.drop_index('idx_name')

# Add FK
op.create_foreign_key('fk_name', 'source', 'target', ['col'], ['id'])

# Drop FK
op.drop_constraint('fk_name', 'table', type_='foreignkey')

# Execute SQL
op.execute("UPDATE table SET column = value")

# Bulk insert
op.bulk_insert(table, [{'col': 'val'}])

🎓 SUMMARY
Alembic Best Practices:

✅ Always review auto-generated migrations
✅ Test migrations locally before production
✅ Backup database before production migrations
✅ Write reversible migrations (implement downgrade)
✅ Keep migrations small and focused
✅ Document complex migrations
✅ Use meaningful names for migrations
✅ Version control migration files
✅ Test rollback procedures
✅ Monitor production migrations

Production Deployment Checklist:

 Backup database
 Review migration SQL
 Test in staging
 Enable maintenance mode
 Run migration with logging
 Verify success
 Smoke test application
 Disable maintenance mode
 Monitor for errors