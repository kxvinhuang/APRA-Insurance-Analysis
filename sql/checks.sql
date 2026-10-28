-- checks.sql
-- Run after load_to_sql.py. Each query should match a number from docs/data_validation.md or docs/cleaning_log.txt.

-- 1. rows per fact table (cleaning log: policy 23797, claims 95245, disputes 78304, industry 19198)
SELECT 'fact_policy' AS table_name, COUNT(*) AS rows FROM fact_policy
UNION ALL SELECT 'fact_claims',   COUNT(*) FROM fact_claims
UNION ALL SELECT 'fact_disputes', COUNT(*) FROM fact_disputes
UNION ALL SELECT 'fact_industry', COUNT(*) FROM fact_industry;

-- 2. value status per fact table (cleaning log: claims value 53783 / masked 40075 / missing 1387, and so on)
SELECT 'fact_policy' AS table_name, value_status, COUNT(*) AS rows FROM fact_policy GROUP BY value_status
UNION ALL SELECT 'fact_claims',   value_status, COUNT(*) FROM fact_claims   GROUP BY value_status
UNION ALL SELECT 'fact_disputes', value_status, COUNT(*) FROM fact_disputes GROUP BY value_status
UNION ALL SELECT 'fact_industry', value_status, COUNT(*) FROM fact_industry GROUP BY value_status
ORDER BY 1, 2;

-- 3. masked and missing rows must never hold a number (should return 0)
SELECT COUNT(*) AS masked_or_missing_with_a_number
FROM (SELECT value_status, value_num FROM fact_policy
      UNION ALL SELECT value_status, value_num FROM fact_claims
      UNION ALL SELECT value_status, value_num FROM fact_disputes
      UNION ALL SELECT value_status, value_num FROM fact_industry) AS all_facts
WHERE value_status <> 'value' AND value_num IS NOT NULL;

-- 4. dimension sizes (expected: 21 companies = 20 insurers + Total, 17 dates, 7 covers, 5 channels)
SELECT (SELECT COUNT(*) FROM dim_company) AS companies,
       (SELECT COUNT(*) FROM dim_company WHERE is_industry_total) AS industry_total_rows,
       (SELECT COUNT(*) FROM dim_date)    AS dates,
       (SELECT COUNT(*) FROM dim_cover)   AS covers,
       (SELECT COUNT(*) FROM dim_channel) AS channels;

-- 5. flagged rows (cleaning log: invalid combo claims 24, disputes 20, industry 4080, out of range policy 3)
SELECT 'fact_policy' AS table_name, COUNT(*) FILTER (WHERE is_invalid_combo) AS invalid_combo,
       COUNT(*) FILTER (WHERE is_out_of_range) AS out_of_range FROM fact_policy
UNION ALL SELECT 'fact_claims',   COUNT(*) FILTER (WHERE is_invalid_combo), COUNT(*) FILTER (WHERE is_out_of_range) FROM fact_claims
UNION ALL SELECT 'fact_disputes', COUNT(*) FILTER (WHERE is_invalid_combo), COUNT(*) FILTER (WHERE is_out_of_range) FROM fact_disputes
UNION ALL SELECT 'fact_industry', COUNT(*) FILTER (WHERE is_invalid_combo), COUNT(*) FILTER (WHERE is_out_of_range) FROM fact_industry;

-- 6. the industry Total must equal the sum of the insurers where every value is visible
-- (validation report: about 354 groups tested for lives insured, 0 mismatches)
WITH g AS (
    SELECT f.date_key, f.channel_id, f.cover_id,
           SUM(f.value_num)    FILTER (WHERE NOT c.is_industry_total) AS insurers,
           MAX(f.value_num)    FILTER (WHERE c.is_industry_total)     AS reported_total,
           BOOL_AND(f.value_status = 'value')                         AS all_visible
    FROM fact_policy f
    JOIN dim_company c USING (company_id)
    JOIN dim_measure m USING (measure_id)
    WHERE m.data_item = 'Lives insured'
    GROUP BY f.date_key, f.channel_id, f.cover_id
)
SELECT COUNT(*) AS groups_tested,
       COUNT(*) FILTER (WHERE reported_total <> 0
                          AND ABS(insurers - reported_total) > 0.001 * reported_total) AS mismatches
FROM g
WHERE all_visible AND reported_total IS NOT NULL;

-- 7. claims reconcile: received = finalised + withdrawn + undetermined
-- (validation report: 2298 testable groups, 0 failed)
WITH w AS (
    SELECT f.date_key, f.company_id, f.channel_id, f.cover_id,
           MAX(f.value_num) FILTER (WHERE cat.category_name = 'Total Claims Received') AS received,
           MAX(f.value_num) FILTER (WHERE cat.category_name = 'Finalised Claims')      AS finalised,
           MAX(f.value_num) FILTER (WHERE cat.category_name = 'Withdrawn Claims')      AS withdrawn,
           MAX(f.value_num) FILTER (WHERE cat.category_name = 'Undetermined Claims')   AS undetermined
    FROM fact_claims f
    JOIN dim_measure m   USING (measure_id)
    JOIN dim_category cat USING (category_id)
    WHERE m.subject = 'Claims' AND m.data_item = 'Number of claims'
    GROUP BY f.date_key, f.company_id, f.channel_id, f.cover_id
)
SELECT COUNT(*) AS testable_groups,
       COUNT(*) FILTER (WHERE received <> finalised + withdrawn + undetermined) AS failed
FROM w
WHERE received IS NOT NULL AND finalised IS NOT NULL AND withdrawn IS NOT NULL AND undetermined IS NOT NULL;

-- 8. share of values hidden by masking, per company (ABN-level, so renamed insurers are one row)
-- just a new check to see which companies have the most masked values
SELECT 'claims' AS sheet, c.company_name, COUNT(*) AS rows,
       ROUND(100.0 * COUNT(*) FILTER (WHERE f.value_status = 'masked') / COUNT(*), 1) AS pct_masked
FROM fact_claims f
JOIN dim_company c USING (company_id)
GROUP BY c.company_name
UNION ALL
SELECT 'disputes', c.company_name, COUNT(*),
       ROUND(100.0 * COUNT(*) FILTER (WHERE f.value_status = 'masked') / COUNT(*), 1)
FROM fact_disputes f
JOIN dim_company c USING (company_id)
GROUP BY c.company_name
ORDER BY sheet, pct_masked DESC;