"""MySQL access for OFS.

Every request opens its own connection, which is fine at this scale. Two
helpers cover almost every use:

    rows = db.query_all("SELECT ... WHERE x = %s", (x,))
    row  = db.query_one("SELECT ... WHERE id = %s", (id,))

and, for anything that writes, a transaction that commits on success and
rolls back if any statement fails, so nothing is ever half-written:

    with db.transaction() as cur:
        cur.execute("UPDATE ...")
        cur.execute("INSERT ...")

DECIMAL columns come back as Python Decimal, never float. The 20 lb
delivery rule depends on that.
"""

import os
from contextlib import contextmanager

import pymysql
from dotenv import load_dotenv
from pymysql.cursors import DictCursor

# Reads backend/.env if present, so nobody has to export credentials by
# hand each session. Real environment variables still win over the file.
load_dotenv()

DB_CONFIG = {
    "host":     os.environ.get("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.environ.get("MYSQL_PORT", "3306")),
    "user":     os.environ.get("MYSQL_USER", "cs160team2"),
    "password": os.environ.get("MYSQL_PASSWORD", ""),
    "database": os.environ.get("MYSQL_DATABASE", "ofs"),
    "charset":  "utf8mb4",
    "cursorclass": DictCursor,
    "autocommit": False,          # explicit commits, see transaction()
}


def get_connection():
    return pymysql.connect(**DB_CONFIG)


def db_version():
    return query_one("SELECT VERSION() AS version")["version"]


def query_all(sql, params=()):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def query_one(sql, params=()):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()


@contextmanager
def transaction():
    """Yield a cursor. Commit if the block finishes, roll back if it
    raises. Use SELECT ... FOR UPDATE inside it to lock rows that two
    requests might change at the same time (stock, mainly)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def placeholders(values):
    """'%s,%s,%s' for an IN (...) clause with one slot per value."""
    return ",".join(["%s"] * len(values))
