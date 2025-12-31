import argparse
import psycopg
import polars as pl


def get_primary_key_columns(conn, table_name):
    query = """
        SELECT a.attname
        FROM pg_index i
        JOIN pg_attribute a
          ON a.attrelid = i.indrelid
         AND a.attnum = ANY(i.indkey)
        WHERE i.indrelid = to_regclass(%s)
          AND i.indisprimary
        ORDER BY array_position(i.indkey, a.attnum)
    """
    with conn.cursor() as cur:
        cur.execute(query, (table_name,))
        rows = cur.fetchall()

    if not rows:
        raise RuntimeError(f"Table {table_name} has no primary key")

    return [r[0] for r in rows]


def fetch_pk_rows(conn, table_name, pk_cols):
    cols = ", ".join(pk_cols)
    query = f"SELECT {cols} FROM {table_name}"

    with conn.cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()

    return pl.from_records(rows, schema=pk_cols)


def show_ranges(conn, table_name, pk_cols, df):
    with conn.cursor() as cur:
        for row in df.iter_rows(named=True):
            values = ", ".join(
                "'" + str(row[col]).replace("'", "''") + "'" for col in pk_cols
            )
            stmt = f"""
                SELECT range_id, lease_holder, replicas, replica_localities FROM [
                    SHOW RANGE FROM TABLE {table_name} FOR ROW ({values})
                ]
                ORDER BY range_id
            """
            cur.execute(stmt)
            ranges = cur.fetchall()

            print(f"\nRow {row}:")
            for r in ranges:
                print(r)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--table", required=True)
    args = parser.parse_args()

    with psycopg.connect(args.url) as conn:
        pk_cols = get_primary_key_columns(conn, args.table)
        df = fetch_pk_rows(conn, args.table, pk_cols)
        show_ranges(conn, args.table, pk_cols, df)


if __name__ == "__main__":
    main()
