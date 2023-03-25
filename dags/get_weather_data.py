from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator

from datetime import datetime, timedelta
import logging
import pandas as pd
import numpy as np

default_args = {
    "owner": "AlexDeLara",
    "retries": 5,
    "retry_delay": timedelta(minutes=2)
}

BASE_OUTPUT_PATH = "/opt/airflow/dags/data/"

def download_weather_data(**kwargs):
    import requests
    import os.path

    base_url = "https://smn.conagua.gob.mx/webservices/?method=1"
    base_output_path = kwargs['base_output_path']

    headers={
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "Cookie": "HttpOnly; _ga=GA1.1.2013713985.1679539354; 6d97cdd4f899b737880dffe8a4fef2bc=ve6b1g4ek9eg8ra584cc6q6in4; HttpOnly; ApplicationGatewayAffinity=bca9cc31b3143085a28e07db54604157e121c61665b54a8ce9a954d588f1a532; ApplicationGatewayAffinityCORS=bca9cc31b3143085a28e07db54604157e121c61665b54a8ce9a954d588f1a532; _ga_40NBLJ6G7W=GS1.1.1679712749.4.1.1679714268.0.0.0", 
        "cp-extension-installed": "Yes",
        "Host": "smn.conagua.gob.mx",
        "sec-ch-ua": '"Google Chrome;v="111", "Not(A:Brand";v="8", "Chromium";v="111"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Linux"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": "Custom"
    }

    def decompress_data(gz_data):
        import gzip

        try:
            logging.info("Decompressing .gz weather data...")
            decompressed_data = gzip.decompress(gz_data)
            logging.info("Decompression successful!")
            return decompressed_data
        except Exception as e:
            raise Exception(f"Could not decompress weather data. {str(e)}")
        
    def parse_json(json_data):
        try:
            logging.info("Parsing json weather data...")
            data = pd.read_json(json_data)
            logging.info("Parsing successful!")
            return data
        except Exception as e:
            raise Exception(f"Could not parse weather data. {str(e)}")


    try:
        response = requests.get(base_url, headers=headers)

        if(response.ok):
            json_data = decompress_data(gz_data=response.content)
            data = parse_json(json_data=json_data)
            data['date_process'] = datetime.now()
            logging.info("Writing current data...")
            data.to_parquet(path=f"{base_output_path}/raw/current_weather_data.parquet", index=False)
            logging.info("Successfully created current_weather_data.parquet file!...")

            logging.info("Appending to historic data...")
            if not(os.path.isfile(f"{base_output_path}/raw/historic_weather_data.parquet")):
                data.to_parquet(path=f"{base_output_path}/raw/historic_weather_data.parquet", index=False)
            else:
                history = pd.read_parquet(path=f"{base_output_path}/raw/historic_weather_data.parquet")
                history = history.append(data)
                history.to_parquet(path=f"{base_output_path}/raw/historic_weather_data.parquet", index=False)
            logging.info("Successfully appended new data to historic_weather_data.parquet file!")
        else:
            raise ValueError(f"Could not retrieve weather data. Response code: {response.status_code}.\nResponse message: {response.text}")

    except Exception as e:
        logging.error(f"An error occurred when trying to retrieve the weather data. Error:\n{str(e)}")
        raise

def agg_weather_data(**kwargs):
    base_output_path = kwargs['base_output_path']
    agg_start_time = datetime.now()

    replace_dict = {
        'á': 'a',
        'é': 'e',
        'í': 'i',
        'ó': 'o',
        'ú': 'u',
        '.': ''
    }

    def clean_name(row):
        for key, val in replace_dict.items():
            row = row.replace(key, val)
        return row

    history = pd.read_parquet(path=f"{base_output_path}/raw/historic_weather_data.parquet", engine="pyarrow")

    history["table_name"] = (history.nes.astype(str) + "_" + history.nmun.astype(str)).str.lower().apply(clean_name)

    for table in history["table_name"].unique():
        mun_data = history.loc[(history["table_name"] == table) & (history["date_process"] >= (agg_start_time + timedelta(hours=-2))), :].copy()
        agg_mun_data = mun_data.groupby(["dloc", "ides", "idmun", "ndia", "nes", "nmun"]).agg({"tmin": np.mean, "tmax": np.mean}).reset_index()
        agg_mun_data['date_process'] = datetime.now()
        agg_mun_data.to_parquet(path=f"{base_output_path}/processed/{table}_avg_t.parquet", index=False)

def merge_weather_data(**kwargs):
    base_output_path = kwargs['base_output_path']

    current_data = pd.read_parquet(path=f"{base_output_path}/raw/current_weather_data.parquet")
    aux_data = pd.read_csv(f"{base_output_path}/current/raw_data_merge.csv")

    merged_data = current_data.merge(aux_data, left_on=["ides", "idmun"], right_on=["Cve_Ent", "Cve_Mun"], how="left")

    merged_data.drop(columns=["Cve_Ent", "Cve_Mun"], inplace=True)

    merged_data.to_parquet(path=f"{base_output_path}/current/current_weather_data_merged")
    

with DAG(
    dag_id="get_weather_data_v0",
    default_args=default_args,
    description="Downloads the latest weather data from https://smn.conagua.gob.mx/es/web-service-api",
    start_date=datetime(2023, 3, 25, 0, 0, 0),
    schedule_interval="0 * * * *",
    catchup=False

) as dag:
    task_download_weather_data = PythonOperator(
        task_id="download_weather_data",
        python_callable=download_weather_data,
        op_kwargs={"base_output_path": BASE_OUTPUT_PATH},
    ) 

    task_agg_weather_data = PythonOperator(
        task_id="agg_weather_data",
        python_callable=agg_weather_data,
        op_kwargs={"base_output_path": BASE_OUTPUT_PATH}
    )

    task_merge_weather_data = PythonOperator(
        task_id="merge_weather_data",
        python_callable=merge_weather_data,
        op_kwargs={"base_output_path": BASE_OUTPUT_PATH}
    )

    task_download_weather_data >> task_agg_weather_data >> task_merge_weather_data

