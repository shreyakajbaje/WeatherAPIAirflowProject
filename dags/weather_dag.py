from airflow import DAG
from datetime import timedelta, datetime, timezone
from airflow.providers.http.sensors.http import HttpSensor
import json
from airflow.providers.http.operators.http import SimpleHttpOperator
from airflow.operators.python import PythonOperator
import pandas as pd
import boto3
from auth import ACCESS_KEY, SECRET_KEY
from io import StringIO
import csv

def kelvin_to_fahrenheit(temp_in_kelvin):
    temp_in_fahrenheit = (temp_in_kelvin - 273.15) * (9/5) + 32
    return temp_in_fahrenheit


def transform_load_data(task_instance):

    # Step 1 - Data Transformation
    data = task_instance.xcom_pull(task_ids="extract_weather_data")
    city = data["name"]
    weather_description = data["weather"][0]['description']
    temp_farenheit = kelvin_to_fahrenheit(data["main"]["temp"])
    feels_like_farenheit= kelvin_to_fahrenheit(data["main"]["feels_like"])
    min_temp_farenheit = kelvin_to_fahrenheit(data["main"]["temp_min"])
    max_temp_farenheit = kelvin_to_fahrenheit(data["main"]["temp_max"])
    pressure = data["main"]["pressure"]
    humidity = data["main"]["humidity"]
    wind_speed = data["wind"]["speed"]
    time_of_record = datetime.fromtimestamp(data['dt'] + data['timezone'])
    sunrise_time = datetime.fromtimestamp(data['sys']['sunrise'] + data['timezone'])
    sunset_time = datetime.fromtimestamp(data['sys']['sunset'] + data['timezone'])

    transformed_data = {"City": city,
                        "Description": weather_description,
                        "Temperature (F)": temp_farenheit,
                        "Feels Like (F)": feels_like_farenheit,
                        "Minimun Temp (F)":min_temp_farenheit,
                        "Maximum Temp (F)": max_temp_farenheit,
                        "Pressure": pressure,
                        "Humidty": humidity,
                        "Wind Speed": wind_speed,
                        "Time of Record": time_of_record,
                        "Sunrise (Local Time)":sunrise_time,
                        "Sunset (Local Time)": sunset_time                        
                        }
    transformed_data_list = [transformed_data]
    df_data = pd.DataFrame(transformed_data_list)
        
    # Step 2 - Write dataframe to csv file and push to aws s3 bucket 

    # aws_credentials = {"key": "", "secret": "", "token": ""}

    now = datetime.now()
    dt_string = now.strftime("%d%m%Y%H%M%S")
    dt_string = 'current_weather_data_pune_' + dt_string
    
    # ----------Method 1 - use to_csv to write csv to s3 bucket----------

    # df_data.to_csv(f"s3://weatherapiairflowproject-yml/{dt_string}.csv", index=False, storage_options=aws_credentials)
    
    # ----------Method 2 - save to local csv file and push to s3 bucket----------
    df_data.to_csv(f"/opt/airflow/logs/{dt_string}.csv", index=False)
    
    client = boto3.client('s3', aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY)
    # with open(f"/opt/airflow/logs/{dt_string}.csv","rb") as f:
    #     client.upload_fileobj(f,"weatherapiairflowproject-yml",f"/opt/airflow/logs/{dt_string}.csv")

    # ----------Method 3 - convert df to string and write string to s3 bucket----------

    # Convert df to string
    csv_string = StringIO()
    csv_writer = csv.writer(csv_string)
    csv_writer.writerows(df_data)

    # Upload CSV string to S3 bucket
    bucket_name = 'weatherapiairflowproject-yml'

    client.put_object(Bucket=bucket_name, Key=dt_string, Body=csv_string.getvalue())

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2024, 5, 20),
    'email': [],
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=2)
}

with DAG('weather_dag',
        default_args=default_args,
        schedule_interval= '@daily',
        catchup=False) as dag:
    
        is_weather_api_ready = HttpSensor(
                task_id = 'is_weather_api_ready',
                http_conn_id= 'weathermap_api',
                endpoint='/data/2.5/weather?q=Pune&appid=f3ab10bd45b1669434c4da7f043b1a5a'
        )

        extract_weather_data = SimpleHttpOperator(
                task_id = 'extract_weather_data',
                http_conn_id= 'weathermap_api',
                endpoint='/data/2.5/weather?q=Pune&appid=f3ab10bd45b1669434c4da7f043b1a5a',
                method='GET',
                response_filter= lambda r: json.loads(r.text),
                log_response= True
        )

        transform_load_weather_data = PythonOperator(
                task_id = 'transform_load_weather_data',
                python_callable=transform_load_data       
        )

        is_weather_api_ready >> extract_weather_data >> transform_load_weather_data