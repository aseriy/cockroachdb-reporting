import datetime as dt
import psycopg
import random
import time
import uuid
import polars as pl


class Datapointhistoricextract:
    def __init__(self, args: dict):
        # args is a dict of string passed with the --args flag
        # user passed a yaml/json, in python that's a dict object
        None

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
                self.sql_full_polars,
                self.sql_full_polars_archive
            ]


  
    def sql_full_polars(self, conn: psycopg.Connection):
        query = f"""
                SELECT
                    d.at,                                                
                    s.id,                                                
                    g.crdb_region,                                       
                    d.param0, d.param1, d.param2, d.param3, d.param4,    
                    d.param5, d.param6                                       
                FROM stations AS s                                       
                JOIN datapoints AS d ON s.id = d.station                                  
                JOIN geos AS g ON g.id = s.geo                                      
                AS OF SYSTEM TIME follower_read_timestamp()
        """

        result = pl.read_database(
            query = query,
            connection = conn,
            iter_batches = True,
            batch_size = 10000
        )


    def sql_full_polars_archive(self, conn: psycopg.Connection):
        query = f"""
                SELECT
                    d.at,                                                
                    s.id,                                                
                    g.crdb_region,                                       
                    d.param0, d.param1, d.param2, d.param3, d.param4,    
                    d.param5, d.param6                                       
                FROM stations AS s                                       
                JOIN datapoints AS d ON s.id = d.station                                  
                JOIN geos AS g ON g.id = s.geo                                      
                AS OF SYSTEM TIME follower_read_timestamp()
                WHERE d.at < now() - INTERVAL '90 days'
        """

        result = pl.read_database(
            query = query,
            connection = conn,
            iter_batches = True,
            batch_size = 10000
        )

