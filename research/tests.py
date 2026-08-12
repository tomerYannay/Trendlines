import pandas as pd
import psycopg2
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Load tickers from the CSV file
df = pd.read_csv("data/russell_tickers_extracted.csv")  # ודא שהקובץ באותה תיקייה או שים נתיב מלא
tickers = df['Ticker'].dropna().unique().tolist()

# Prepare DB connection
db_config = {
    'dbname': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USERNAME'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT')
}

# Insert into tickers_russell table
insert_sql = """
    INSERT INTO tickers_russell (ticker)
    VALUES (%s)
    ON CONFLICT (ticker) DO NOTHING;
"""

with psycopg2.connect(**db_config) as conn:
    with conn.cursor() as cursor:
        cursor.executemany(insert_sql, [(ticker,) for ticker in tickers])
        conn.commit()

print(f"✅ Inserted {len(tickers)} tickers into tickers_russell")
