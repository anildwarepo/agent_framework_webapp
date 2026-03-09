import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def log(message: str) -> None:
    print(message, flush=True)


def main() -> None:
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

    dsn = dict(
        host=os.getenv("PGHOST", "localhost"),
        port=int(os.getenv("PGPORT", "5432")),
        dbname=os.getenv("PGDATABASE", "postgres"),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", "postgres"),
        sslmode=os.getenv("PGSSLMODE", "require"),
        connect_timeout=int(os.getenv("PGCONNECT_TIMEOUT", "20")),
    )
    schema = "customer_graph"
    plan_log_every = int(os.getenv("INDEX_PLAN_LOG_EVERY", "50"))
    commit_every_tables = int(os.getenv("INDEX_COMMIT_EVERY_TABLES", "100"))
    sql_filename = f"create_{schema}_indexes.sql"
    log(f"Starting index build for schema: {schema}")
    log("Connecting to PostgreSQL...")

    with psycopg.connect(**dsn) as conn:
        log("Connected")
        with conn.cursor() as cur:
            log("Applying session timeouts...")
            cur.execute("SET statement_timeout = '60s';")
            cur.execute("SET lock_timeout = '5s';")
            cur.execute("SET idle_in_transaction_session_timeout = '60s';")

            log("Ensuring AGE extension...")
            cur.execute("CREATE EXTENSION IF NOT EXISTS AGE CASCADE;")
            has_pg_trgm = True
            try:
                log("Checking pg_trgm extension...")
                cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
            except Exception:
                has_pg_trgm = False
                conn.rollback()
                log("pg_trgm unavailable; continuing without trigram indexes")
                cur.execute("CREATE EXTENSION IF NOT EXISTS AGE CASCADE;")
                cur.execute("SET statement_timeout = '60s';")
                cur.execute("SET lock_timeout = '5s';")
                cur.execute("SET idle_in_transaction_session_timeout = '60s';")
            log("Setting search_path...")
            cur.execute('SET search_path = ag_catalog, "$user", public;')

            log(f"Discovering tables in schema {schema}...")
            cur.execute(
                """
                SELECT c.relname
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = %s
                  AND c.relkind = 'r'
                ORDER BY c.relname;
                """,
                (schema,),
            )
            tables = [row[0] for row in cur.fetchall()]
            log(f"Found {len(tables)} tables")

            log("Loading column metadata for all tables...")
            cur.execute(
                """
                SELECT table_name, column_name
                FROM information_schema.columns
                WHERE table_schema = %s;
                """,
                (schema,),
            )
            metadata_rows = cur.fetchall()
            table_columns: dict[str, set[str]] = {}
            for table_name, column_name in metadata_rows:
                table_columns.setdefault(table_name, set()).add(column_name)
            log(f"Loaded {len(metadata_rows)} column metadata rows")

            table_statements: list[tuple[str, list[str]]] = []

            total_tables = len(tables)
            for table_index, table in enumerate(tables, start=1):
                if table_index == 1 or table_index % plan_log_every == 0 or table_index == total_tables:
                    log(f"Planning indexes [{table_index}/{total_tables}] {table}")

                quoted_schema = quote_ident(schema)
                quoted_table = quote_ident(table)
                base_name = f"{table.lower()}"
                cols = table_columns.get(table, set())

                table_stmts: list[str] = []

                if "id" in cols:
                    table_stmts.append(
                        f"CREATE INDEX IF NOT EXISTS idx_{base_name}_id ON {quoted_schema}.{quoted_table} (id);"
                    )
                if "start_id" in cols:
                    table_stmts.append(
                        f"CREATE INDEX IF NOT EXISTS idx_{base_name}_start_id ON {quoted_schema}.{quoted_table} (start_id);"
                    )
                if "end_id" in cols:
                    table_stmts.append(
                        f"CREATE INDEX IF NOT EXISTS idx_{base_name}_end_id ON {quoted_schema}.{quoted_table} (end_id);"
                    )
                if "properties" in cols:
                    table_stmts.append(
                        f"CREATE INDEX IF NOT EXISTS idx_{base_name}_props_gin ON {quoted_schema}.{quoted_table} USING GIN (((properties::text)::jsonb));"
                    )
                    table_stmts.append(
                        f"CREATE INDEX IF NOT EXISTS idx_{base_name}_payload_gin ON {quoted_schema}.{quoted_table} USING GIN ((((properties::text)::jsonb -> 'payload')));"
                    )
                    if has_pg_trgm:
                        table_stmts.append(
                            f"CREATE INDEX IF NOT EXISTS idx_{base_name}_payload_name_trgm ON {quoted_schema}.{quoted_table} USING GIN (lower((((properties::text)::jsonb -> 'payload' ->> 'name'))) gin_trgm_ops);"
                        )
                    else:
                        table_stmts.append(
                            f"CREATE INDEX IF NOT EXISTS idx_{base_name}_payload_name_lower ON {quoted_schema}.{quoted_table} (lower((((properties::text)::jsonb -> 'payload' ->> 'name'))));"
                        )

                table_statements.append((table, table_stmts))

            statements = [stmt for _, stmts in table_statements for stmt in stmts]

            log("Writing SQL plan file...")
            sql_file = Path(__file__).with_name(sql_filename)
            sql_file.write_text("\n".join(statements) + "\n", encoding="utf-8")

            applied = 0
            failed = 0
            total_index_tables = len(table_statements)
            for table_index, (table_name, stmts) in enumerate(table_statements, start=1):
                if not stmts:
                    log(f"[{table_index}/{total_index_tables}] {table_name}: no indexable columns found")
                    continue

                log(f"[{table_index}/{total_index_tables}] {table_name}: creating {len(stmts)} indexes")
                for stmt_index, stmt in enumerate(stmts, start=1):
                    try:
                        cur.execute(stmt)
                        applied += 1
                        log(f"  ({stmt_index}/{len(stmts)}) OK")
                    except Exception as exc:
                        failed += 1
                        conn.rollback()
                        cur.execute("CREATE EXTENSION IF NOT EXISTS AGE CASCADE;")
                        cur.execute("SET statement_timeout = '60s';")
                        cur.execute("SET lock_timeout = '5s';")
                        cur.execute("SET idle_in_transaction_session_timeout = '60s';")
                        cur.execute('SET search_path = ag_catalog, "$user", public;')
                        log(f"  ({stmt_index}/{len(stmts)}) FAILED: {exc}")

                if table_index % commit_every_tables == 0:
                    log(f"Checkpoint commit at table {table_index}/{total_index_tables}")
                    conn.commit()

            log("Committing index changes...")
            conn.commit()

    log(f"Schema: {schema}")
    log(f"Tables indexed: {len(tables)}")
    log(f"Index statements applied: {applied}")
    log(f"Index statements failed: {failed}")
    log(f"pg_trgm available: {has_pg_trgm}")
    log(f"SQL written to {sql_filename}")


if __name__ == "__main__":
    main()
