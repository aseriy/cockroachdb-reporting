import argparse
from sqlalchemy import create_engine, text
import polars as pl


def get_primary_key_columns(engine, table_name):
    query = text("""
        SELECT a.attname
        FROM pg_index i
        JOIN pg_attribute a
          ON a.attrelid = i.indrelid
         AND a.attnum = ANY(i.indkey)
        WHERE i.indrelid = to_regclass(:table)
          AND i.indisprimary
        ORDER BY array_position(i.indkey, a.attnum)
    """)
    with engine.connect() as conn:
        rows = conn.execute(query, {"table": table_name}).fetchall()

    if not rows:
        raise RuntimeError(f"Table {table_name} has no primary key")

    return [r[0] for r in rows]


def fetch_pk_rows(engine, table_name, pk_cols):
    cols = ", ".join(pk_cols)
    query = f"SELECT {cols} FROM {table_name}"

    with engine.connect() as conn:
        result = conn.execute(text(query))
        df = pl.from_records(result.fetchall(), schema=pk_cols)

    return df


def show_ranges(engine, table_name, pk_cols, df):
    with engine.connect() as conn:
        for row in df.iter_rows(named=True):
            values = ", ".join(
                "'" + str(row[col]).replace("'", "''") + "'" for col in pk_cols
            )
            stmt = text(
                f"""SELECT range_id, lease_holder, replicas, replica_localities FROM [
                            SHOW RANGE FROM TABLE {table_name} FOR ROW ({values})
                        ]
                    ORDER by range_id
                """
            )
            ranges = conn.execute(stmt).fetchall()

            print(f"\nRow {row}:")
            for r in ranges:
                print(r)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-url", required=True)
    parser.add_argument("--table", required=True)
    args = parser.parse_args()

    engine = create_engine(args.db_url)

    pk_cols = get_primary_key_columns(engine, args.table)
    df = fetch_pk_rows(engine, args.table, pk_cols)
    show_ranges(engine, args.table, pk_cols, df)


if __name__ == "__main__":
    main()
