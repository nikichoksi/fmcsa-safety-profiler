import sqlite3
import pandas as pd

conn = sqlite3.connect("database/fmcsa.db")

# How many active carriers?
print(pd.read_sql("SELECT COUNT(*) FROM carriers WHERE status_code = 'A'", conn))

# Sample carriers
print(pd.read_sql("SELECT * FROM carriers LIMIT 3", conn))

# Inspection date range
print(pd.read_sql("SELECT MIN(insp_date), MAX(insp_date) FROM inspections", conn))

# Sample inspections
print(pd.read_sql("SELECT * FROM inspections LIMIT 3", conn))

conn.close()