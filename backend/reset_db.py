"""Rebuild the OFS tables and seed data from schema.sql.

schema.sql is still the file to run once in MySQL Workbench, as root,
because only root can create the cs160team2 account. After that, this
script lets anyone wipe and re-seed a database without opening Workbench:

    python reset_db.py            # rebuilds the database named in .env (ofs)
    python reset_db.py ofs_test   # rebuilds the test database

The test suite calls load_tables() itself before every test, against
ofs_test, so tests never touch the data in ofs.
"""

import os
import sys
from pathlib import Path

import pymysql

import db

SCHEMA_FILE = Path(__file__).with_name("schema.sql")


def table_statements():
    """The statements between the @@TABLES@@ and @@END_TABLES@@ markers
    in schema.sql, one string per statement."""
    text = SCHEMA_FILE.read_text(encoding="utf-8")
    body = text.split("@@TABLES@@", 1)[1].split("@@END_TABLES@@", 1)[0]

    statements, current = [], []
    for line in body.splitlines():
        if line.strip().startswith("--"):
            continue
        current.append(line)
        if line.rstrip().endswith(";"):
            statements.append("\n".join(current).strip().rstrip(";"))
            current = []
    return [s for s in statements if s]


def load_tables(database):
    """Drop and recreate every table in `database`, then seed it."""
    config = {**db.DB_CONFIG, "database": None, "autocommit": True}
    conn = pymysql.connect(**config)
    try:
        with conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS `{database}`")
            cur.execute(
                f"CREATE DATABASE `{database}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            cur.execute(f"USE `{database}`")
            for statement in table_statements():
                cur.execute(statement)
    finally:
        conn.close()


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("MYSQL_DATABASE", "ofs")
    load_tables(target)
    print(f"Rebuilt database '{target}' from {SCHEMA_FILE.name}")
