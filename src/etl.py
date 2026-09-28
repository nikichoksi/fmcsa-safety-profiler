import pandas as pd
import sqlite3
from pathlib import Path

DB_PATH = "database/fmcsa.db"

def get_conn():
    Path("database").mkdir(exist_ok=True)
    return sqlite3.connect(DB_PATH)

def run_schema():
    conn = get_conn()
    schema = """
    DROP TABLE IF EXISTS carriers;
    DROP TABLE IF EXISTS inspections;
    DROP TABLE IF EXISTS violations;
    DROP TABLE IF EXISTS crashes;
    
    CREATE TABLE carriers (
        dot_number INTEGER PRIMARY KEY,
        legal_name TEXT,
        dba_name TEXT,
        carrier_operation TEXT,
        hm_flag INTEGER,
        pc_flag INTEGER,
        phy_state TEXT,
        phy_city TEXT,
        total_drivers INTEGER,
        total_power_units INTEGER,
        mcs150_mileage INTEGER,
        mcs150_mileage_year INTEGER,
        status_code TEXT,
        safety_rating TEXT
    );
    CREATE TABLE inspections (
        inspection_id INTEGER PRIMARY KEY,
        dot_number INTEGER,
        insp_date TEXT,
        insp_state TEXT,
        insp_level INTEGER,
        weight TEXT,
        hazmat_inspected INTEGER,
        oos_total INTEGER,
        oos_vehicle INTEGER,
        oos_driver INTEGER
    );
    CREATE TABLE violations (
        violation_id INTEGER PRIMARY KEY AUTOINCREMENT,
        inspection_id INTEGER,
        dot_number INTEGER,
        violation_code TEXT,
        violation_desc TEXT,
        oos_indicator TEXT,
        severity_weight INTEGER,
        unit_type TEXT
    );
    CREATE TABLE crashes (
        crash_id INTEGER PRIMARY KEY,
        dot_number INTEGER,
        report_date TEXT,
        report_state TEXT,
        fatalities INTEGER,
        injuries INTEGER,
        tow_away TEXT,
        hazmat_released TEXT
    );
    """
    conn.executescript(schema)
    conn.close()
    print("✅ Schema created")

def find_file(folder, keywords):
    folder = Path(folder)
    for f in folder.iterdir():
        name_lower = f.name.lower()
        if any(k in name_lower for k in keywords) and f.suffix in ['.csv', '.txt']:
            return f
    raise FileNotFoundError(f"No file found matching {keywords} in {folder}")

def map_columns(df, mappings):
    col_map = {}
    used_targets = set()
    for target, possible_names in mappings:
        if target in used_targets:
            continue
        for orig_col in df.columns:
            if orig_col in col_map:
                continue
            clean = str(orig_col).strip().upper().replace(' ', '_')
            if clean in possible_names:
                col_map[orig_col] = target
                used_targets.add(target)
                break
    return col_map

def load_census():
    filepath = find_file("data", ["census", "motor carrier census"])
    print(f"Loading census from {filepath.name}...")
    df = pd.read_csv(filepath, low_memory=False)
    
    mappings = [
        ('dot_number', ['DOT_NUMBER', 'USDOT_NUMBER', 'USDOT_NUM', 'DOT_NUM']),
        ('legal_name', ['LEGAL_NAME', 'NAME']),
        ('dba_name', ['DBA_NAME', 'DOING_BUSINESS_AS']),
        ('carrier_operation', ['CARRIER_OPERATION', 'OPERATION']),
        ('hm_flag', ['HM_FLAG', 'HAZMAT_FLAG']),
        ('pc_flag', ['PC_FLAG', 'PASSENGER_CARRIER_FLAG']),
        ('phy_state', ['PHY_STATE', 'PHYSICAL_STATE', 'STATE']),
        ('phy_city', ['PHY_CITY', 'PHYSICAL_CITY', 'CITY']),
        ('total_drivers', ['TOTAL_DRIVERS', 'DRIVERS', 'NUMBER_OF_DRIVERS']),
        ('total_power_units', ['TOTAL_POWER_UNITS', 'POWER_UNITS', 'NUMBER_OF_POWER_UNITS']),
        ('mcs150_mileage', ['MCS150_MILEAGE', 'MILEAGE']),
        ('mcs150_mileage_year', ['MCS150_MILEAGE_YEAR', 'MILEAGE_YEAR']),
        ('status_code', ['STATUS_CODE', 'STATUS', 'ENTITY_STATUS']),
        ('safety_rating', ['SAFETY_RATING', 'RATING']),
    ]
    
    col_map = map_columns(df, mappings)
    print(f"   Mapped: {list(col_map.values())}")
    df = df.rename(columns=col_map)
    
    needed = ['dot_number', 'legal_name', 'dba_name', 'carrier_operation',
              'hm_flag', 'pc_flag', 'phy_state', 'phy_city',
              'total_drivers', 'total_power_units', 'mcs150_mileage',
              'mcs150_mileage_year', 'status_code', 'safety_rating']
    available = [c for c in needed if c in df.columns]
    df = df[available]
    
    conn = get_conn()
    df.to_sql('carriers', conn, if_exists='replace', index=False)
    conn.close()
    print(f"   → {len(df):,} carriers loaded")

def load_inspections():
    filepath = find_file("data", ["inspection", "safetynet"])
    print(f"Loading inspections from {filepath.name}...")
    df = pd.read_csv(filepath, low_memory=False)
    
    mappings = [
        ('inspection_id', ['UNIQUE_ID', 'INSPECTION_ID', 'ID']),
        ('dot_number', ['DOT_NUMBER', 'USDOT_NUMBER', 'USDOT_NUM']),
        ('insp_date', ['INSP_DATE', 'INSPECTION_DATE', 'DATE']),
        ('insp_state', ['INSP_STATE', 'INSPECTION_STATE', 'STATE']),
        ('insp_level', ['INSP_LEVEL_ID', 'INSP_LEVEL', 'LEVEL_ID', 'LEVEL']),
        ('weight', ['WEIGHT']),
        ('hazmat_inspected', ['HAZMAT_INSP', 'HAZMAT_INSPECTED', 'HAZMAT']),
        ('oos_total', ['OOS_TOTAL', 'TOTAL_OOS']),
        ('oos_vehicle', ['OOS_VEHICLE', 'VEHICLE_OOS']),
        ('oos_driver', ['OOS_DRIVER', 'DRIVER_OOS']),
    ]
    
    col_map = map_columns(df, mappings)
    print(f"   Mapped: {list(col_map.values())}")
    df = df.rename(columns=col_map)
    if 'insp_date' in df.columns:
        df['insp_date'] = pd.to_datetime(df['insp_date'], errors='coerce')
    
    needed = ['inspection_id', 'dot_number', 'insp_date', 'insp_state',
              'insp_level', 'weight', 'hazmat_inspected', 'oos_total',
              'oos_vehicle', 'oos_driver']
    available = [c for c in needed if c in df.columns]
    df = df[available]
    
    conn = get_conn()
    df.to_sql('inspections', conn, if_exists='replace', index=False)
    conn.close()
    print(f"   → {len(df):,} inspections loaded")

def load_violations():
    filepath = find_file("data", ["violation"])
    print(f"Loading violations from {filepath.name}...")
    df = pd.read_csv(filepath, low_memory=False)
    
    mappings = [
        ('inspection_id', ['UNIQUE_ID', 'INSPECTION_ID', 'ID']),
        ('dot_number', ['DOT_NUMBER', 'USDOT_NUMBER', 'USDOT_NUM']),
        ('violation_code', ['VIOLATION_CODE', 'CODE']),
        ('violation_desc', ['BASIC_DESC', 'VIOLATION_DESC', 'DESCRIPTION', 'DESC']),
        ('oos_indicator', ['OOS_INDICATOR', 'OOS']),
        ('severity_weight', ['SEVERITY_WEIGHT', 'SEVERITY']),
        ('unit_type', ['UNIT_TYPE', 'UNIT']),
    ]
    
    col_map = map_columns(df, mappings)
    print(f"   Mapped: {list(col_map.values())}")
    df = df.rename(columns=col_map)
    
    needed = ['inspection_id', 'dot_number', 'violation_code', 'violation_desc',
              'oos_indicator', 'severity_weight', 'unit_type']
    available = [c for c in needed if c in df.columns]
    df = df[available]
    
    conn = get_conn()
    df.to_sql('violations', conn, if_exists='replace', index=False)
    conn.close()
    print(f"   → {len(df):,} violations loaded")

def load_crashes():
    filepath = find_file("data", ["crash"])
    print(f"Loading crashes from {filepath.name}...")
    df = pd.read_csv(filepath, low_memory=False)
    
    mappings = [
        ('crash_id', ['REPORT_NUM', 'CRASH_ID', 'ID', 'UNIQUE_ID']),
        ('dot_number', ['DOT_NUMBER', 'USDOT_NUMBER', 'USDOT_NUM']),
        ('report_date', ['REPORT_DATE', 'CRASH_DATE', 'DATE']),
        ('report_state', ['REPORT_STATE', 'CRASH_STATE', 'STATE']),
        ('fatalities', ['FATALITIES']),
        ('injuries', ['INJURIES']),
        ('tow_away', ['TOW_AWAY', 'TOWAWAY']),
        ('hazmat_released', ['HAZMAT_RELEASED', 'HAZMAT']),
    ]
    
    col_map = map_columns(df, mappings)
    print(f"   Mapped: {list(col_map.values())}")
    df = df.rename(columns=col_map)
    if 'report_date' in df.columns:
        df['report_date'] = pd.to_datetime(df['report_date'], errors='coerce')
    
    needed = ['crash_id', 'dot_number', 'report_date', 'report_state',
              'fatalities', 'injuries', 'tow_away', 'hazmat_released']
    available = [c for c in needed if c in df.columns]
    df = df[available]
    
    conn = get_conn()
    df.to_sql('crashes', conn, if_exists='replace', index=False)
    conn.close()
    print(f"   → {len(df):,} crashes loaded")

def create_indexes():
    print("Creating indexes...")
    conn = get_conn()
    conn.execute("CREATE INDEX IF NOT EXISTS idx_insp_dot ON inspections(dot_number)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_viol_dot ON violations(dot_number)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_viol_insp ON violations(inspection_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_crash_dot ON crashes(dot_number)")
    conn.commit()
    conn.close()
    print("✅ Indexes created")

def main():
    run_schema()
    load_census()
    load_inspections()
    load_violations()
    load_crashes()
    create_indexes()
    print("\n🎉 Database ready at:", DB_PATH)

if __name__ == "__main__":
    main()