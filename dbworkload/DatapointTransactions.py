import datetime as dt
import psycopg
import random
import time
import uuid
from datetime import datetime, timedelta
import string
import json
from sentence_transformers import SentenceTransformer

class Datapointoltp:

    def __init__(self, args: dict):
        # args is a dict of string passed with the --args flag
        # user passed a yaml/json, in python that's a dict object

        self.init_random_ranges = {
            "interval": {
                "low": 0,
                "high": 60
            },
            "date": {
                "low": datetime(2024,1,1),
                "high": datetime(datetime.now().year, 12, 31)
            },
            "param0": {
                "low": 0,
                "high": 1000
            },
            "param1": {
                "low": -1000,
                "high": 1000
            },
            "param2": {
                "low": -1000,
                "high": 1000,
                "precision": 3
            },
            "param3": {
                "low": -1000,
                "high": 1000,
                "precision": 2
            },
            "param4": {
                "low": 8,
                "high": 32
            }
        }




    def embed_text(self, text: str):
        model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        emb = model.encode([text])
        return emb[0].tolist()


    def random_date(self, d1, d2):
        retval = None
        date_range = d2 - d1
        retval = d1 + timedelta(
                                    days = random.randint(0, date_range.days),
                                    hours = random.randint(0, 24),
                                    minutes = random.randint(0, 60),
                                    seconds = random.uniform(0, 60)
                                )
        return retval.strftime("%Y-%m-%d %H:%M:%S.%f")


    def random_string(self, length: int, chars: str) -> str:
        return ''.join(random.choices(chars, k=length))


    def random_json_object(self, depth=1, max_fields=4):
        obj = {}
        for _ in range(random.randint(1, max_fields)):
            key = self.random_string(random.randint(3, 10), string.ascii_lowercase)
            value_type = random.choice(['str', 'int', 'float', 'bool', 'null', 'nested'])

            if value_type == 'str':
                value = self.random_string(random.randint(3, 12), string.ascii_letters)
            elif value_type == 'int':
                value = random.randint(0, 1000)
            elif value_type == 'float':
                value = round(random.uniform(0, 1000), 3)
            elif value_type == 'bool':
                value = random.choice([True, False])
            elif value_type == 'null':
                value = None
            elif value_type == 'nested' and depth > 0:
                value = self.random_json_object(depth=depth-1, max_fields=max_fields)
            else:
                value = "unknown"

            obj[key] = value
        return obj


    def create_datapoint(self, conn: psycopg.Connection):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT s.id, g.crdb_region FROM stations AS s JOIN geos AS g on s.geo = g.id ORDER BY random() LIMIT 1"
            )
            (station_id, station_region) = cur.fetchone()


        datapoint = {
            "interval": random.randint(
                            self.init_random_ranges['interval']['low'],
                            self.init_random_ranges['interval']['high']
                        ),
            "station":  str(station_id),
            "region":   str(station_region),
            "date":     self.random_date(
                            self.init_random_ranges['date']['low'],
                            self.init_random_ranges['date']['high']
                        ),
            "param0":   random.randint(
                            self.init_random_ranges['param0']['low'],
                            self.init_random_ranges['param0']['high']
                        ),
            "param1":   random.randint(
                            self.init_random_ranges['param1']['low'],
                            self.init_random_ranges['param1']['high']
                        ),
            "param2":   round(random.uniform(
                            self.init_random_ranges['param2']['low'],
                            self.init_random_ranges['param2']['high']
                        ), self.init_random_ranges['param2']['precision']),
            "param3":   round(random.uniform(
                            self.init_random_ranges['param3']['low'],
                            self.init_random_ranges['param3']['high']
                        ), self.init_random_ranges['param3']['precision']),
            "param4":   ''.join(random.choices(
                            string.ascii_uppercase + string.digits,
                            k = random.randint(
                                self.init_random_ranges['param4']['low'],
                                self.init_random_ranges['param4']['high']
                            ))),
            "param5":   json.dumps(self.random_json_object(
                                        random.randint(1,10),
                                        random.randint(1,10)
                                    ))
        }

        datapoint_text = "/".join([
            str(datapoint["param0"]),
            str(datapoint["param1"]),
            str(datapoint["param2"]),
            str(datapoint["param3"]),
            str(datapoint["param4"]),
            str(datapoint["param5"])
        ])
        vec = self.embed_text(datapoint_text)
        datapoint["param6"] = "[" + ",".join(str(x) for x in vec) + "]"

        return datapoint



    # the setup() function is executed only once
    # when a new executing thread is started.
    # Also, the function is a vector to receive the excuting threads's unique id and the total thread count
    def setup(self, conn: psycopg.Connection, id: int, total_thread_count: int):
        with conn.cursor() as cur:
            print(
                f"My thread ID is {id}. The total count of threads is {total_thread_count}"
            )
            print(cur.execute(f"select version()").fetchone()[0])



    # the run() function returns a list of functions
    # that dbworkload will execute, sequentially.
    # Once every func has been executed, run() is re-evaluated.
    # This process continues until dbworkload exits.
    def loop(self):
        return [
                self.sql_insert_datapoint
            ]


    def sql_insert_datapoint(self, conn: psycopg.Connection):
        datapoint = self.create_datapoint(conn)
        # print(json.dumps(datapoint, indent=2))

        with conn.cursor() as cur:
            sql = """
                UPSERT INTO datapoints
                    (
                        station, at,
                        crdb_region,
                        param0, param1, param2, param3, param4, param5, param6
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            # print(sql)
            cur.execute(sql, (
                    datapoint["station"], datapoint['date'],
                    datapoint["region"],
                    datapoint['param0'], datapoint['param1'],
                    datapoint['param2'], datapoint['param3'],
                    datapoint["param4"], datapoint['param5'],
                    datapoint["param6"]
                )
            )

