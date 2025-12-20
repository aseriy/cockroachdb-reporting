import datetime as dt
import psycopg
import random
import time
import uuid
import json
from DatapointTransactions import Datapointtransactions


class Datapointvectorsearch:
    def __init__(self, args: dict):
        self.datapoint = Datapointtransactions({})


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
                self.sql_find_similar_datapoints
            ]


    def datapoint_str(self, dp) -> str:
        return "/".join([
            str(dp["param0"]),
            str(dp["param1"]),
            str(dp["param2"]),
            str(dp["param3"]),
            str(dp["param4"]),
            str(dp["param5"])
        ])


  
    def sql_find_similar_datapoints(self, conn: psycopg.Connection):
        datapoint = self.datapoint.create_datapoint(conn)
        # print(json.dumps(datapoint, indent=2))


        vector = datapoint["param6"]
        
        query = f"""
                SELECT
                    station,
                    at,
                    param0,
                    param1,
                    param2,
                    param3,
                    param4,
                    param5,
                    param6 <=> %s AS distance
                FROM datapoints
                ORDER BY param6 <=> %s
                LIMIT 10;
        """

        with conn.cursor() as cur:
            cur.execute(query, (vector,vector))
            result = cur.fetchall()
        
        # print(f"\t\t\t{self.datapoint_str(datapoint)}\n")
        # for r in result:
        #     rdp = {
        #         "param0":   r[2],
        #         "param1":   r[3],
        #         "param2":   r[4],
        #         "param3":   r[5],
        #         "param4":   r[6],
        #         "param5":   r[7],
        #     }
        #     print(f"{r[8]}\t{self.datapoint_str(rdp)}\n")


