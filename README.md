# Weather data ETL  
## Data Extraction
- Each hour, the weather data is downloaded from https://smn.conagua.gob.mx/es/web-service-api. The data is decompressed from a .gz compression format and the resulting JSON is parsed into tabular form using pandas.  
- The raw data is then stored in the /dags/data/raw directory. The most recent data is saved as current_weather_data.parquet and it is also appended to the historic data file, named historic_weathed_data.parquet.  
- Each file is loaded with and addition date_process column to determine the date of processing.  

## Data Transformation I  
- After download, the last 2 hours of data are filtered using the date_process field form the historic weather file.  
- The data is aggregated by state and municipality to calculate the AVG min and max temperature of the last 2 hours of data extracted.  
- One .parquet file is created by municipality. The naming follows the standard <state_name>_<municipality_name>.parquet.  
- Every two hours these files are overwritten. No aggregate historic data is stored, but could easily be computed if needed using the raw historic weather file.  

## Data Transformation II  
- As a last step, the current weahter data file is merged with the given .csv file (/dags/data/current/raw_data_merge.csv)  
- The resulting file is saved at dags/data/current/current_weather_data_merged.parquet  

# Installation
- The project is created using Docker Compose and Airflow  
- After downloading the project, cd into the main directory of it  
- Run the following commands:  

```
$ docker compose up airflow-init
$ docker compose up
```  

- The container will be initialized  

# Airflow GUI  
- The Airflow GUI can be accessed at http://localhost:8080/  
- Username and password are both _airflow_  
- There is a single DAG available that orchestrates each one of the ETL tasks  
- Logs are provided for each DAG execution with custom additional logging information  
- Enable the DAG and trigger a manual execution if necessary  
- **IMPORTANT**: If execution fails, DO NOT force another manual execution. Otherwise, the service will reject the connection. Wait at least 5-10 minutes to retry  

## Sidenotes
- Due to permission errors, the output data folder was created inside the dags folder  
- To redirect the outputs to a new folder, a new env volume can be created and the global variable BASE_OUTPUT_PATH in the get_weather_data.py DAG modified  
- Airflow LocalExecutor is used instead of CeleryExecutor for testing simplification  
