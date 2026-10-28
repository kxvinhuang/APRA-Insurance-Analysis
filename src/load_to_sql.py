import csv
import os
from pathlib import Path
import psycopg2
from dotenv import load_dotenv

PROCESSED = Path("data/processed")
SCHEMA_SQL = Path("sql/schema.sql")
LOAD_SQL = Path("sql/load.sql")

# staging table, the cleaned csv copied into it, and the table whose row count it must match once loaded
STAGING = [
    ("stg_policy", "policy_stats.csv", "fact_policy"),
    ("stg_claims", "claims.csv", "fact_claims"),
    ("stg_disputes", "disputes.csv", "fact_disputes"),
    ("stg_industry", "industry_stats.csv", "fact_industry"),
    ("stg_company_names", "company_names.csv", "company_name_history"),
]


def count_csv_rows(path):
    # number of data rows in a csv, using the csv module so quoted fields are counted properly
    with open(path, newline="", encoding="utf-8") as f:
        return sum(1 for _ in csv.reader(f)) - 1


def copy_csv(cur, table, path):
    with open(path, newline="", encoding="utf-8") as f:
        # the first line holds the column names, which match the staging table's column names
        header = next(csv.reader(f))
        # go back to the start so COPY can skip the header line itself
        f.seek(0)
        # COPY adds the whole file into the table in one go which is faster than inserting row by row
        cur.copy_expert(f"COPY {table} ({', '.join(header)}) FROM STDIN WITH (FORMAT csv, HEADER true)", f)


def main():
    # read the connection details from the .env file (host, port, database, user, password)
    load_dotenv()
    missing = [name for _, name, _ in STAGING if not (PROCESSED / name).exists()]
    if missing:
        raise FileNotFoundError(f"missing in {PROCESSED}: {missing} - run src/clean_data.py first")

    conn = psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"), port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE"), user=os.getenv("PGUSER"), password=os.getenv("PGPASSWORD"))
    try:
        # everything below is one transaction: it commits only if every step works,
        # and rolls back to the previous state if anything fails
        with conn, conn.cursor() as cur:
            cur.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
            for table, name, _ in STAGING:
                copy_csv(cur, table, PROCESSED / name)
            cur.execute(LOAD_SQL.read_text(encoding="utf-8"))

            # every csv row must have become exactly one row in its table, inner joins would drop any that did not match
            print(f"{'table':<25}{'csv rows':>10}{'loaded':>10}")
            for _, name, target in STAGING:
                expected = count_csv_rows(PROCESSED / name)
                cur.execute(f"SELECT COUNT(*) FROM {target}")
                loaded = cur.fetchone()[0]
                print(f"{target:<25}{expected:>10}{loaded:>10}")
                if loaded != expected:
                    raise RuntimeError(f"{target}: {expected} csv rows but {loaded} loaded, resetting database")

            print("\ndimension tables:")
            for table in ["dim_date", "dim_company", "dim_channel", "dim_cover", "dim_category", "dim_measure"]:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                print(f"  {table:<15}{cur.fetchone()[0]:>7}")
        print("\nload committed")
    finally:
        conn.close()


if __name__ == "__main__":
    main()