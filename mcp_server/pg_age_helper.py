# pg_age_helper.py

import os, asyncio, json, re
import psycopg
from psycopg import sql
from psycopg.rows import dict_row   # 👈 NEW
from dotenv import load_dotenv
from typing import Any, List

load_dotenv()

DSN = dict(
    host=os.getenv("PGHOST", "localhost"),
    port=int(os.getenv("PGPORT", "5432")),
    dbname=os.getenv("PGDATABASE", "postgres"),
    user=os.getenv("PGUSER", "postgres"),
    password=os.getenv("PGPASSWORD", "postgres"),
)

GRAPH = os.getenv("GRAPH")

if not GRAPH:
    raise ValueError("GRAPH environment variable must be set")


class PGAgeHelper:
    def __init__(self, conn: psycopg.AsyncConnection):
        self._conn = conn
        self.graph = GRAPH

    @classmethod
    async def create(cls) -> "PGAgeHelper":
        # row_factory=dict_row -> rows become dicts instead of tuples
        conn = await psycopg.AsyncConnection.connect(**DSN, row_factory=dict_row)
        
        async with conn.cursor() as cur:
            await cur.execute("SELECT 1 FROM pg_extension WHERE extname='age';")
            if not await cur.fetchone():
                await conn.close()
                raise RuntimeError(
                    "AGE extension is not installed in this database. "
                    "Run as superuser: CREATE EXTENSION age;"
                )
            await cur.execute('SET search_path = ag_catalog, "$user", public;')

        return cls(conn)

    @staticmethod
    def _normalize_cypher_query(query: str) -> str:
        """
        Ensure we always call ag_catalog.cypher(...) instead of bare cypher(...).
        """
        # Matches FROM cypher( or JOIN cypher( with optional whitespace
        pattern = r'\b(FROM|JOIN)\s+cypher\s*\('
        replacement = r'\1 ag_catalog.cypher('
        return re.sub(pattern, replacement, query, flags=re.IGNORECASE)

    async def query_using_sql_cypher(self, query: str) -> list[dict]:
        query = self._normalize_cypher_query(query)
        print("Executing query:\n", query)

        try:
            async with self._conn.cursor() as cur:
                await cur.execute(query)
                rows = await cur.fetchall()
                print("Raw rows:", rows)
                return rows
        except Exception as e:
            print("Error executing query:", e)
            try:
                print("Attempting to rollback transaction...")
                await self._conn.rollback()
                print("Rollback successful.")
            except Exception:
                # If rollback itself failed, you may need to reconnect upstream
                pass
            raise

   

#if __name__ == "__main__":
#    asyncio.run(main())
