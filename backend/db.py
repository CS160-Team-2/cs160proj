import os
from contextlib import contextmanager

import pymysql
from dotenv import load_dotenv
from pymysql.cursors import DictCursor

load_dotenv()

DB_CONFIG = {
    "host":     os.environ.get("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.environ.get("MYSQL_PORT", "3306")),
    "user":     os.environ.get("MYSQL_USER", "cs160team2"),
    "password": os.environ.get("MYSQL_PASSWORD", ""),
    "database": os.environ.get("MYSQL_DATABASE", "ofs"),
    "charset":  "utf8mb4",
    "cursorclass": DictCursor,
    "autocommit": False,
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


# Yield a cursor.
@contextmanager
def transaction():
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


# '%s,%s,%s' for an IN (...) clause with one slot per value.
def placeholders(values):
    return ",".join(["%s"] * len(values))
