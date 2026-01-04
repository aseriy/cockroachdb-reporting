import argparse
import psycopg
import polars as pl
import json


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

    stream = pl.read_database(
        query = query,
        connection = conn,
        iter_batches = True,
        batch_size = 1000
    )

    range_stats = {}

    for batch in stream:
        print(batch)
        with conn.cursor() as cur:
            for row in batch.iter_rows(named=True):
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
                data = parse_row_info(row, ranges)
                merge_stats(range_stats, data)
                # print(range_stats)

    return range_stats



def merge_stats(range_stats, data):
    for range_id, data in data.items():
        entry = range_stats.setdefault(
            range_id,
            {
                "replicas": set(),
                "leaseholder": None,
                "rows": 0
            },
        )

        entry["rows"] += 1

        for replica in data.get("replicas", []):
            entry["replicas"].add(tuple(replica))

        if "leaseholder" in data:
            entry["leaseholder"] = tuple(data["leaseholder"])



def parse_row_info(row, ranges):
    data = {}
    # print(f"\nRow {row}:")
    for r in ranges:
        range_id, leaseholder, replicas, replica_locations = r

        data[range_id] = {
            "replicas": tuple(sorted(
                            ((x.split("=", 1)[1], r) for x, r in zip(replica_locations, replicas)),
                            key=lambda t: t[0]
                        ))
        }

        data[range_id]["leaseholder"] = next(t for t in data[range_id]["replicas"] if t[1] == leaseholder)

    return data


def print_range_table(range_stats):
    rows = []
    total_rows = 0

    for i, (range_id, d) in enumerate(sorted(range_stats.items()), start=1):
        total_rows += d["rows"]
        rows.append([
            str(i),                         # row number
            str(range_id),
            str(d["rows"]),
            f"{d['leaseholder'][0]} ({d['leaseholder'][1]})",
            ", ".join(f"{n} ({s})" for n, s in sorted(d["replicas"])),
        ])

    headers = ["", "range_id", "rows", "leaseholder", "replicas"]

    # totals row
    rows.append([
        "",                                # no row number
        "TOTAL",
        str(total_rows),
        "",
        "",
    ])

    # compute widths (no truncation)
    cols = list(zip(*([headers] + rows)))
    widths = [max(len(v) for v in col) for col in cols]

    def line(left, mid, right):
        return left + mid.join("─" * (w + 2) for w in widths) + right

    def row_line(values):
        return "│ " + " │ ".join(v.ljust(w) for v, w in zip(values, widths)) + " │"

    print(line("┌", "┬", "┐"))
    print(row_line(headers))
    print(line("╞", "╪", "╡"))

    for r in rows[:-1]:
        print(row_line(r))

    print(line("├", "┼", "┤"))
    print(row_line(rows[-1]))
    print(line("└", "┴", "┘"))




def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--table", required=True)
    args = parser.parse_args()

    with psycopg.connect(args.url) as conn:
        pk_cols = get_primary_key_columns(conn, args.table)
        stats = fetch_pk_rows(conn, args.table, pk_cols)
        print_range_table(stats)


if __name__ == "__main__":
    main()
