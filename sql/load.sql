-- load.sql
-- Builds the dimensions and facts from the staging tables, then drops the staging tables.

-- ---------------------------------------------------------------------------------------------
-- Dimensions
-- ---------------------------------------------------------------------------------------------

-- every reporting date that appears in any sheet
INSERT INTO dim_date (date_key, year, month, period_label, is_calendar_year_end)
SELECT d,
       EXTRACT(YEAR FROM d)::INT,
       EXTRACT(MONTH FROM d)::INT,
       TO_CHAR(d, 'Mon YYYY'),
       EXTRACT(MONTH FROM d) = 12
FROM (SELECT reporting_date AS d FROM stg_policy
      UNION SELECT reporting_date FROM stg_claims
      UNION SELECT reporting_date FROM stg_disputes
      UNION SELECT reporting_date FROM stg_industry) AS all_dates
ORDER BY d;

-- one row per ABN, using the name with the latest last_date as the display name
INSERT INTO dim_company (abn, company_name, is_industry_total)
SELECT DISTINCT ON (abn) abn, company_name, FALSE
FROM stg_company_names
ORDER BY abn, last_date DESC;

-- the industry Total company has no ABN
INSERT INTO dim_company (abn, company_name, is_industry_total) VALUES (NULL, 'Total', TRUE);

-- every name each ABN has used
INSERT INTO company_name_history (company_id, company_name, first_date, last_date, is_latest_name)
SELECT c.company_id, s.company_name, s.first_date, s.last_date, s.is_latest_name
FROM stg_company_names s
JOIN dim_company c ON c.abn = s.abn;

INSERT INTO dim_channel (channel_name, is_total_channel)
SELECT channel_type, channel_type = 'Total'
FROM (SELECT channel_type FROM stg_policy
      UNION SELECT channel_type FROM stg_claims
      UNION SELECT channel_type FROM stg_disputes
      UNION SELECT channel_type FROM stg_industry) AS x
ORDER BY channel_type;

INSERT INTO dim_cover (cover_name)
SELECT cover_type
FROM (SELECT cover_type FROM stg_policy
      UNION SELECT cover_type FROM stg_claims
      UNION SELECT cover_type FROM stg_disputes
      UNION SELECT cover_type FROM stg_industry) AS x
ORDER BY cover_type;

-- category 0 is the 'no category' row used by facts that have no category
INSERT INTO dim_category (category_id, category_name, is_total_category) VALUES (0, '(none)', FALSE);

INSERT INTO dim_category (category_name, is_total_category)
SELECT category, LOWER(category) = 'total'
FROM (SELECT category FROM stg_claims
      UNION SELECT category FROM stg_disputes
      UNION SELECT category FROM stg_industry) AS x
WHERE category IS NOT NULL
ORDER BY category;

-- a measure is a subject plus a data item
-- if one pair ever had two units the UNIQUE constraint would stop the load, which is what we want
INSERT INTO dim_measure (subject, data_item, calculation_basis, unit, is_additive)
SELECT DISTINCT subject, data_item, calculation_basis, unit,
       -- counts and dollar totals can be summed across insurers, rates, averages and shares cannot
       data_item IN ('Lives insured', 'Annual premium', 'Sum insured', 'Number of claims',
                     'Total finalised claims', 'Number of disputes', 'Total disputes resolved',
                     'Number of reasons')
FROM (SELECT subject, data_item, calculation_basis, unit FROM stg_policy
      UNION ALL SELECT subject, data_item, calculation_basis, unit FROM stg_claims
      UNION ALL SELECT subject, data_item, calculation_basis, unit FROM stg_disputes
      UNION ALL SELECT subject, data_item, calculation_basis, unit FROM stg_industry) AS x;

-- ---------------------------------------------------------------------------------------------
-- Facts
-- these are inner joins, so a row with no matching dimension row would be dropped
-- load_to_sql.py compares the row counts with the csv files and rolls everything back if they differ
-- ---------------------------------------------------------------------------------------------

INSERT INTO fact_policy (date_key, company_id, channel_id, cover_id, measure_id,
                         value_num, value_status, is_invalid_combo, is_out_of_range)
SELECT s.reporting_date, co.company_id, ch.channel_id, cv.cover_id, m.measure_id,
       s.value_num, s.value_status, s.is_invalid_combo, s.is_out_of_range
FROM stg_policy s
-- the Total company has no ABN, so match on the flag and compare ABNs in a way that treats NULL = NULL
JOIN dim_company co ON co.is_industry_total = s.is_industry_total AND co.abn IS NOT DISTINCT FROM s.abn
JOIN dim_channel ch ON ch.channel_name = s.channel_type
JOIN dim_cover   cv ON cv.cover_name   = s.cover_type
JOIN dim_measure m  ON m.subject = s.subject AND m.data_item = s.data_item;

INSERT INTO fact_claims (date_key, company_id, channel_id, cover_id, measure_id, category_id,
                         value_num, value_status, is_invalid_combo, is_out_of_range)
SELECT s.reporting_date, co.company_id, ch.channel_id, cv.cover_id, m.measure_id, cat.category_id,
       s.value_num, s.value_status, s.is_invalid_combo, s.is_out_of_range
FROM stg_claims s
JOIN dim_company  co  ON co.is_industry_total = s.is_industry_total AND co.abn IS NOT DISTINCT FROM s.abn
JOIN dim_channel  ch  ON ch.channel_name = s.channel_type
JOIN dim_cover    cv  ON cv.cover_name   = s.cover_type
JOIN dim_measure  m   ON m.subject = s.subject AND m.data_item = s.data_item
-- rows with no category join to the '(none)' row
JOIN dim_category cat ON cat.category_name = COALESCE(s.category, '(none)');

INSERT INTO fact_disputes (date_key, company_id, channel_id, cover_id, measure_id, category_id,
                           value_num, value_status, is_invalid_combo, is_out_of_range)
SELECT s.reporting_date, co.company_id, ch.channel_id, cv.cover_id, m.measure_id, cat.category_id,
       s.value_num, s.value_status, s.is_invalid_combo, s.is_out_of_range
FROM stg_disputes s
JOIN dim_company  co  ON co.is_industry_total = s.is_industry_total AND co.abn IS NOT DISTINCT FROM s.abn
JOIN dim_channel  ch  ON ch.channel_name = s.channel_type
JOIN dim_cover    cv  ON cv.cover_name   = s.cover_type
JOIN dim_measure  m   ON m.subject = s.subject AND m.data_item = s.data_item
JOIN dim_category cat ON cat.category_name = COALESCE(s.category, '(none)');

INSERT INTO fact_industry (date_key, channel_id, cover_id, measure_id, category_id,
                           value_num, value_status, is_invalid_combo, is_out_of_range)
SELECT s.reporting_date, ch.channel_id, cv.cover_id, m.measure_id, cat.category_id,
       s.value_num, s.value_status, s.is_invalid_combo, s.is_out_of_range
FROM stg_industry s
JOIN dim_channel  ch  ON ch.channel_name = s.channel_type
JOIN dim_cover    cv  ON cv.cover_name   = s.cover_type
JOIN dim_measure  m   ON m.subject = s.subject AND m.data_item = s.data_item
JOIN dim_category cat ON cat.category_name = COALESCE(s.category, '(none)');

-- the staging tables are no longer needed
DROP TABLE stg_policy, stg_claims, stg_disputes, stg_industry, stg_company_names;