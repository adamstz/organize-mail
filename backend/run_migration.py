#!/usr/bin/env python3
"""Run database migrations for mail-organizer.

Usage:
    python run_migration.py <migration_file>
    
Example:
    python run_migration.py src/storage/migrations/001_add_fulltext_search.sql
"""

import sys
import os
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from src.storage.postgres_storage import get_db_url
import psycopg2


def run_migration(sql_file: str):
    """Run a SQL migration file."""
    if not os.path.exists(sql_file):
        print(f"Error: Migration file not found: {sql_file}")
        sys.exit(1)
    
    print(f"Reading migration file: {sql_file}")
    with open(sql_file, 'r') as f:
        sql_content = f.read()
    
    print(f"Connecting to database...")
    db_url = get_db_url()
    conn = psycopg2.connect(db_url)
    
    try:
        print(f"Executing migration...")
        cur = conn.cursor()
        cur.execute(sql_content)
        conn.commit()
        cur.close()
        print(f"✓ Migration completed successfully!")
        
    except Exception as e:
        print(f"✗ Migration failed: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_migration.py <migration_file>")
        print("\nAvailable migrations:")
        migrations_dir = Path(__file__).parent / "src" / "storage" / "migrations"
        if migrations_dir.exists():
            for migration in sorted(migrations_dir.glob("*.sql")):
                print(f"  - {migration.relative_to(Path(__file__).parent)}")
        sys.exit(1)
    
    migration_file = sys.argv[1]
    run_migration(migration_file)
