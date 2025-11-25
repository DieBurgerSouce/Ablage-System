# Database Seed Command

You are helping seed the database with test or development data.

## Your Task

Create and execute a comprehensive database seeding strategy:

1. **Analyze Current Schema**
   - Read all Alembic migration files
   - Identify all tables and relationships
   - Determine required data for each table

2. **Create Seed Script**
   - Location: `scripts/seed_db.py`
   - Use async SQLAlchemy for performance
   - Include:
     - User accounts (admin, regular users)
     - Sample documents
     - OCR processing results
     - Realistic German text data
     - Various document statuses

3. **Data Characteristics**
   - German language data (proper umlauts)
   - Realistic timestamps (varied, not all identical)
   - Valid foreign key relationships
   - Mix of completed, pending, and failed statuses
   - Representative metadata fields

4. **Script Features**
   - Idempotent (safe to run multiple times)
   - Clear progress logging
   - Transaction support (all-or-nothing)
   - CLI arguments:
     - `--users N` - Number of users to create
     - `--documents N` - Documents per user
     - `--clean` - Drop all data first
     - `--production-safe` - Prevent running in production

5. **Execute Seeding**
   - Run the script
   - Verify data was created correctly
   - Show summary statistics

## Example Seed Data

```python
SAMPLE_GERMAN_DOCUMENTS = [
    "Rechnung Nr. 2024-001 für Büromaterial",
    "Lieferschein vom 15.03.2024 - Müller GmbH",
    "Jahresabschluss 2023 - Gewinn- und Verlustrechnung",
]

SAMPLE_USERS = [
    {"email": "admin@ablage.local", "role": "admin"},
    {"email": "user1@ablage.local", "role": "user"},
]
```

## Output

Provide:
1. Complete seed script code
2. Execution instructions
3. Verification queries
4. Summary of seeded data
