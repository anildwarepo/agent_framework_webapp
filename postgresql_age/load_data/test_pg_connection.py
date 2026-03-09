import os
import psycopg
from dotenv import load_dotenv


# load environment variables from .env file in folder .azure





load_dotenv()
#pg_host = "kgpgsqlvvlv.postgres.database.azure.com"
#pg_user = "kgadmin"
print("Testing PostgreSQL connection with the following parameters:")
print(f"Host: {os.environ.get('PGHOST', 'localhost')}")
print(f"Port: {os.environ.get('PGPORT', '5432')}")
print(f"Database: {os.environ.get('PGDATABASE', 'postgres')}")
print(f"User: {os.environ.get('PGUSER', 'postgres')}")

try:
    conn = psycopg.connect(
        host=os.environ.get('PGHOST', 'localhost'),
        port=int(os.environ.get('PGPORT', '5432')),
        dbname=os.environ.get('PGDATABASE', 'postgres'),
        user=os.environ.get('PGUSER', 'postgres'),
        password=os.environ.get('PGPASSWORD', ''),
        sslmode=os.environ.get('PGSSLMODE', 'require'),
    )

    print("Connection to PostgreSQL successful. Now checking for AGE extension...")
except Exception as e:
    print("Failed to connect to PostgreSQL:", str(e))
    exit(1) 

conn.autocommit = True
with conn.cursor() as cur:
    cur.execute("CREATE EXTENSION IF NOT EXISTS AGE CASCADE;")
    cur.execute("ALTER DATABASE postgres SET search_path = ag_catalog, \"$user\", public;")
    print("Successfully connected to PostgreSQL and ensured AGE extension is available.")
conn.close()