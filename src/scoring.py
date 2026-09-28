import sqlite3
import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans

DB_PATH = "database/fmcsa.db"

def calculate_safety_scores():
    conn = sqlite3.connect(DB_PATH)

    query = """
    WITH insp AS (
        SELECT dot_number, COUNT(DISTINCT inspection_id) AS inspections
        FROM inspections
        GROUP BY dot_number
    ),
    viol AS (
        SELECT i.dot_number,
               COUNT(v.inspection_id) AS violations,
               SUM(CASE WHEN v.oos_indicator = 1 THEN 1 ELSE 0 END) AS oos_violations,
               COUNT(DISTINCT CASE WHEN v.oos_indicator = 1 THEN v.inspection_id END) AS oos_inspections,
               SUM(v.severity_weight) AS total_severity
        FROM inspections i
        JOIN violations v ON i.inspection_id = v.inspection_id
        GROUP BY i.dot_number
    ),
    crash AS (
        SELECT dot_number,
               COUNT(DISTINCT report_date || '-' || report_state) AS crashes,
               SUM(COALESCE(fatalities, 0)) AS fatalities,
               SUM(COALESCE(injuries, 0)) AS injuries
        FROM crashes
        GROUP BY dot_number
    )
    SELECT
        c.dot_number,
        c.legal_name,
        c.phy_state,
        c.total_power_units,
        c.total_drivers,
        insp.inspections,
        viol.violations,
        viol.oos_violations,
        viol.oos_inspections,
        viol.total_severity,
        crash.crashes,
        crash.fatalities,
        crash.injuries
    FROM carriers c
    JOIN insp ON c.dot_number = insp.dot_number
    LEFT JOIN viol ON c.dot_number = viol.dot_number
    LEFT JOIN crash ON c.dot_number = crash.dot_number
    WHERE c.status_code = 'A'
      AND c.total_power_units > 0
      AND insp.inspections >= 3
    """

    print("Running query (this may take 5-15 minutes)...")
    df = pd.read_sql(query, conn)
    print(f"Query complete. {len(df):,} carriers scored.")
    conn.close()

    df = df.fillna(0)

    # Raw rates (shown in dashboard)
    df['violation_rate_raw'] = (df['violations'] / df['inspections']).round(3)
    df['oos_rate_raw'] = (df['oos_inspections'] / df['inspections']).round(3)
    df['severity_rate_raw'] = (df['total_severity'] / df['inspections']).round(2)
    df['crash_rate_raw'] = (df['crashes'] / df['total_power_units'] * 100).round(3)
    df['crash_rate_raw'] = df['crash_rate_raw'].clip(upper=50)

    # Empirical Bayes shrinkage for OOS rate (used for tiering only)
    global_oos_mean = df['oos_rate_raw'].mean()
    prior_weight = 10
    df['oos_rate'] = (
        (df['oos_inspections'] + prior_weight * global_oos_mean) /
        (df['inspections'] + prior_weight)
    ).round(3)

    # Same shrinkage for severity rate
    global_sev_mean = df['severity_rate_raw'].mean()
    df['severity_rate'] = (
        (df['total_severity'] + prior_weight * global_sev_mean) /
        (df['inspections'] + prior_weight)
    ).round(2)

    # Shrinkage for crash rate (used for tiering only)
    global_crash_mean = df['crash_rate_raw'].mean()
    prior_fleet_weight = 20
    df['crash_rate'] = (
        (df['crashes'] + prior_fleet_weight * global_crash_mean / 100) /
        (df['total_power_units'] + prior_fleet_weight) * 100
    ).round(3)
    df['crash_rate'] = df['crash_rate'].clip(upper=50)

    # Crash percentiles: only among carriers WITH crashes, using shrunk rate
    crash_carriers = df[df['crashes'] > 0]
    crash_p75 = crash_carriers['crash_rate'].quantile(0.75) if len(crash_carriers) > 0 else 999
    crash_p90 = crash_carriers['crash_rate'].quantile(0.90) if len(crash_carriers) > 0 else 999

    # Peer clustering
    fleet_features = np.log1p(df[['total_power_units', 'total_drivers']].fillna(0))
    scaler = StandardScaler()
    fleet_scaled = scaler.fit_transform(fleet_features)

    kmeans = KMeans(n_clusters=4, random_state=42, n_init=10)
    clusters = kmeans.fit_predict(fleet_scaled)

    labels = ['Small Fleet', 'Medium Fleet', 'Large Fleet', 'Extra Large Fleet']
    size_order = df.groupby(clusters)['total_power_units'].mean().sort_values().index
    df['peer_group'] = pd.Series(clusters, index=df.index).map(dict(zip(size_order, labels)))

    # Percentile thresholds from shrunken rates
    oos_p75 = df['oos_rate'].quantile(0.75)
    oos_p90 = df['oos_rate'].quantile(0.90)
    oos_p95 = df['oos_rate'].quantile(0.95)

    sev_p75 = df['severity_rate'].quantile(0.75)
    sev_p90 = df['severity_rate'].quantile(0.90)
    sev_p95 = df['severity_rate'].quantile(0.95)

    print("Percentile thresholds computed:")
    print(f"  OOS rate: 75th={oos_p75:.1%}, 90th={oos_p90:.1%}, 95th={oos_p95:.1%}")
    print(f"  Severity: 75th={sev_p75:.1f}, 90th={sev_p90:.1f}, 95th={sev_p95:.1f}")
    print(f"  Crash rate (crash-only, shrunk): 75th={crash_p75:.2f}, 90th={crash_p90:.2f}")

    # Percentile-based risk tier scoring
    def assign_tier(row):
        score = 0

        if row['oos_rate'] >= oos_p95: score += 3
        elif row['oos_rate'] >= oos_p90: score += 2
        elif row['oos_rate'] >= oos_p75: score += 1

        if row['severity_rate'] >= sev_p95: score += 3
        elif row['severity_rate'] >= sev_p90: score += 2
        elif row['severity_rate'] >= sev_p75: score += 1

        if row['crashes'] > 0:
            if row['crash_rate'] >= crash_p90: score += 2
            elif row['crash_rate'] >= crash_p75: score += 1

        if row['fatalities'] > 0: score += 1

        if score >= 6: return 'Critical'
        elif score >= 4: return 'High'
        elif score >= 2: return 'Medium'
        else: return 'Low'

    df['risk_tier'] = df.apply(assign_tier, axis=1)

    # Save to database
    print("Saving scores to database...")
    conn = sqlite3.connect(DB_PATH)
    df.to_sql('safety_scores', conn, if_exists='replace', index=False)
    conn.close()
    print("Done! Scores saved to 'safety_scores' table.")

    return df

if __name__ == "__main__":
    scores = calculate_safety_scores()
    print("\nRisk Tier Distribution:")
    print(scores['risk_tier'].value_counts())
    print("\nCritical carriers by inspection count:")
    print(scores[scores['risk_tier'] == 'Critical']['inspections'].describe())