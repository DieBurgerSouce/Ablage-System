"""
Example Usage - Vault Integration
Demonstrates how to use Vault in Ablage-System
"""

import os
from infrastructure.vault.vault_client import (
    VaultClient,
    VaultConfig,
    get_secret,
    set_secret,
    get_vault_client
)


# ============================================
# Example 1: Basic Secret Management
# ============================================

def example_basic_secrets():
    """Basic secret read/write operations."""

    # Initialize Vault client
    vault = VaultClient(
        url="http://localhost:8200",
        token=os.getenv('VAULT_TOKEN')
    )

    # Write a secret
    vault.set_secret('ablage-system/my-secret', {
        'key1': 'value1',
        'key2': 'value2',
        'password': 'super_secret'
    })

    # Read entire secret
    secret = vault.get_secret('ablage-system/my-secret')
    print(f"Full secret: {secret}")

    # Read specific key
    password = vault.get_secret('ablage-system/my-secret', key='password')
    print(f"Password: {password}")

    # List secrets
    secrets = vault.list_secrets('ablage-system')
    print(f"Available secrets: {secrets}")


# ============================================
# Example 2: Convenience Functions
# ============================================

def example_convenience_functions():
    """Using convenience functions."""

    # Set environment variable
    os.environ['VAULT_TOKEN'] = 'your-vault-token'

    # Get secret using convenience function
    db_password = get_secret('ablage-system/database', key='password')
    print(f"Database password: {db_password}")

    # Set secret using convenience function
    set_secret('ablage-system/api-keys', {
        'openai': 'sk-...',
        'sentry': 'https://...',
    })


# ============================================
# Example 3: Configuration Loader
# ============================================

def example_config_loader():
    """Using VaultConfig for application configuration."""

    # Load configuration from Vault
    config = VaultConfig(base_path='ablage-system')

    # Access database config
    print(f"Database host: {config.database.host}")
    print(f"Database port: {config.database.port}")
    print(f"Database name: {config.database.database}")
    print(f"Database user: {config.database.username}")
    print(f"Database password: {config.database.password}")

    # Access MinIO config
    print(f"MinIO endpoint: {config.minio.endpoint}")
    print(f"MinIO access key: {config.minio.access_key}")

    # Access application secrets
    print(f"Secret key: {config.app.secret_key}")
    print(f"JWT secret: {config.app.jwt_secret}")

    # Get as dictionary
    db_config = config.database.to_dict()
    print(f"Full database config: {db_config}")


# ============================================
# Example 4: FastAPI Integration
# ============================================

from fastapi import FastAPI, Depends
from typing import Dict, Any

app = FastAPI()

def get_vault_config() -> VaultConfig:
    """Dependency to get Vault configuration."""
    return VaultConfig()

@app.get("/config/database")
async def get_database_config(config: VaultConfig = Depends(get_vault_config)):
    """Get database configuration from Vault."""
    return {
        "host": config.database.host,
        "port": config.database.port,
        "database": config.database.database,
        # Don't return password in API response!
    }

@app.on_event("startup")
async def load_secrets():
    """Load secrets from Vault on application startup."""
    global app_config

    config = VaultConfig()

    # Load all configuration
    app_config = {
        'database': config.database.to_dict(),
        'minio': config.minio.to_dict(),
        'redis': config.redis.to_dict(),
        'app': config.app.to_dict(),
    }

    print("✅ Configuration loaded from Vault")


# ============================================
# Example 5: Dynamic Database Credentials
# ============================================

def example_dynamic_credentials():
    """Using Vault's dynamic database credentials."""

    vault = get_vault_client()

    # Generate dynamic credentials
    creds = vault.get_database_credentials(role='ablage-backend')

    print(f"Username: {creds['username']}")
    print(f"Password: {creds['password']}")
    print(f"Lease ID: {creds['lease_id']}")
    print(f"Lease duration: {creds['lease_duration']} seconds")

    # Use credentials
    connection_string = f"postgresql://{creds['username']}:{creds['password']}@postgres:5432/ablage_system"

    # Renew lease before it expires
    vault.renew_lease(creds['lease_id'], increment=3600)

    # Revoke credentials when done
    vault.revoke_lease(creds['lease_id'])


# ============================================
# Example 6: Environment Variable Loading
# ============================================

def load_env_from_vault():
    """Load environment variables from Vault."""

    config = VaultConfig()

    # Database
    os.environ['DATABASE_URL'] = f"postgresql://{config.database.username}:{config.database.password}@{config.database.host}:{config.database.port}/{config.database.database}"

    # MinIO
    os.environ['MINIO_ENDPOINT'] = config.minio.endpoint
    os.environ['MINIO_ACCESS_KEY'] = config.minio.access_key
    os.environ['MINIO_SECRET_KEY'] = config.minio.secret_key

    # Redis
    os.environ['REDIS_URL'] = f"redis://:{config.redis.password}@{config.redis.host}:{config.redis.port}/0"

    # Application
    os.environ['SECRET_KEY'] = config.app.secret_key
    os.environ['JWT_SECRET'] = config.app.jwt_secret

    # Sentry
    os.environ['SENTRY_DSN'] = config.sentry.dsn
    os.environ['SENTRY_ENVIRONMENT'] = config.sentry.environment

    print("✅ Environment variables loaded from Vault")


# ============================================
# Example 7: Celery Worker Configuration
# ============================================

from celery import Celery

def configure_celery_from_vault():
    """Configure Celery worker using Vault secrets."""

    config = VaultConfig()

    # Create Celery app
    celery_app = Celery('ablage-worker')

    # Configure from Vault
    celery_app.conf.update(
        broker_url=f"redis://:{config.redis.password}@{config.redis.host}:{config.redis.port}/0",
        result_backend=f"redis://:{config.redis.password}@{config.redis.host}:{config.redis.port}/0",

        # Database connection
        sqlalchemy_database_uri=f"postgresql://{config.database.username}:{config.database.password}@{config.database.host}:{config.database.port}/{config.database.database}"
    )

    return celery_app


# ============================================
# Example 8: Secret Rotation
# ============================================

def rotate_database_password():
    """Rotate database password in Vault."""

    import secrets

    vault = get_vault_client()

    # Generate new password
    new_password = secrets.token_urlsafe(32)

    # Get current database config
    db_config = vault.get_secret('ablage-system/database')

    # Update password in Vault
    db_config['password'] = new_password
    vault.set_secret('ablage-system/database', db_config)

    # TODO: Update password in actual database
    # This would connect to PostgreSQL and run:
    # ALTER USER ablage_user WITH PASSWORD 'new_password';

    print(f"✅ Database password rotated")


# ============================================
# Example 9: Error Handling
# ============================================

from hvac.exceptions import VaultError, InvalidPath

def example_error_handling():
    """Proper error handling for Vault operations."""

    vault = get_vault_client()

    try:
        # Try to read non-existent secret
        secret = vault.get_secret('non-existent/path')

    except InvalidPath:
        print("Secret not found - creating default")

        # Create default secret
        vault.set_secret('non-existent/path', {
            'default_key': 'default_value'
        })

    except VaultError as e:
        print(f"Vault error: {e}")
        # Fallback to environment variables or fail gracefully


# ============================================
# Example 10: Health Check
# ============================================

def check_vault_health():
    """Check if Vault is accessible and unsealed."""

    try:
        vault = get_vault_client()

        # Check if authenticated
        if not vault.client.is_authenticated():
            return {
                'status': 'unhealthy',
                'reason': 'Not authenticated'
            }

        # Check seal status
        seal_status = vault.client.sys.read_seal_status()

        if seal_status['sealed']:
            return {
                'status': 'unhealthy',
                'reason': 'Vault is sealed'
            }

        return {
            'status': 'healthy',
            'vault_url': vault.url,
            'version': seal_status.get('version'),
            'cluster_name': seal_status.get('cluster_name')
        }

    except Exception as e:
        return {
            'status': 'unhealthy',
            'reason': str(e)
        }


# ============================================
# Example 11: Batch Operations
# ============================================

def batch_secret_operations():
    """Perform batch secret operations."""

    vault = get_vault_client()

    # Secrets to create
    secrets = {
        'ablage-system/service-a': {
            'api_key': 'key-a',
            'endpoint': 'http://service-a'
        },
        'ablage-system/service-b': {
            'api_key': 'key-b',
            'endpoint': 'http://service-b'
        },
        'ablage-system/service-c': {
            'api_key': 'key-c',
            'endpoint': 'http://service-c'
        }
    }

    # Create all secrets
    for path, data in secrets.items():
        vault.set_secret(path, data)
        print(f"Created: {path}")

    # Read all secrets
    all_secrets = {}
    for path in secrets.keys():
        all_secrets[path] = vault.get_secret(path)

    return all_secrets


if __name__ == '__main__':
    # Run examples
    print("=" * 50)
    print("Example 1: Basic Secrets")
    print("=" * 50)
    example_basic_secrets()

    print("\n" + "=" * 50)
    print("Example 3: Config Loader")
    print("=" * 50)
    example_config_loader()

    print("\n" + "=" * 50)
    print("Example 10: Health Check")
    print("=" * 50)
    health = check_vault_health()
    print(f"Vault health: {health}")
