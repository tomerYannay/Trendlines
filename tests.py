import time
import numpy as np
import requests
from psycopg2.extras import execute_values
import pandas as pd
import psycopg2

from dotenv import load_dotenv
import os

# Load environment variables from the .env file
load_dotenv()

# Get the database credentials from the environment variables
db_username = os.getenv('DB_USERNAME')
db_password = os.getenv('DB_PASSWORD')
db_host = os.getenv('DB_HOST')
db_port = os.getenv('DB_PORT')
db_name = os.getenv('DB_NAME')

db_config = {
    'dbname': db_name,      # Name of your database
    'user': db_username,          # Your PostgreSQL username
    'password': db_password, # Your PostgreSQL password
    'host': db_host,         # Hostname (localhost for local)
    'port': db_port                 # Default PostgreSQL port
}

# Connect to the database
connection = psycopg2.connect(**db_config)
cursor = connection.cursor()




def calculate_sequence(breakthrough_series):
    """Calculate sequence of TRUE values in breakthrough column."""
    sequence = []
    count = 0
    for value in breakthrough_series:
        if value:
            count += 1
        else:
            count = 0
        sequence.append(count)
    return sequence
