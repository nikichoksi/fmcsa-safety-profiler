import sqlite3
import pandas as pd
from pathlib import Path

DB_PATH = "database/fmcsa.db"
EXPORT_PATH = "data/safety_scores.parquet"

conn = sqlite3.connect(DB_PATH)
df = pd.read_sql("SELECT * FROM safety_scores", conn)
conn.close()

df.to_parquet(EXPORT_PATH, index=False, compression='zstd')
print(f"Exported {len(df):,} rows to {EXPORT_PATH}")
print(f"File size: {Path(EXPORT_PATH).stat().st_size / 1024 / 1024:.1f} MB")
