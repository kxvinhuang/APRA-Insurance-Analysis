-- views.sql
-- The fact tables are long (one row per measure and category), so each view
-- pivots one sheet into a wide table with one row per date, company, channel and cover.
-- The views hold IDs only, Power BI gets the names from dim_date, dim_company, dim_channel and dim_cover.
--
-- Rules built into every view:
--   masked and missing values stay NULL, never 0
--   rows in cover/channel combinations APRA says cannot exist (is_invalid_combo) are left out
--   MAX() picks the single value in each group, there is only ever one row per group and measure

DROP VIEW IF EXISTS v_policy, v_claims, v_claims_duration, v_disputes, v_industry_reasons, v_industry_ratios, v_masking;

-- ---------------------------------------------------------------------------------------------
-- Policy statistics: lives insured, premium, market share, new business and lapse
-- values flagged as out of range (the negative lapse rates) are left out
-- ---------------------------------------------------------------------------------------------
CREATE VIEW v_policy AS
SELECT f.date_key, f.company_id, f.channel_id, f.cover_id,
       MAX(f.value_num) FILTER (WHERE m.data_item = 'Lives insured')                  AS lives_insured,
       MAX(f.value_num) FILTER (WHERE m.data_item = 'Annual premium')                 AS annual_premium,
       MAX(f.value_num) FILTER (WHERE m.data_item = 'Sum insured')                    AS sum_insured,
       MAX(f.value_num) FILTER (WHERE m.data_item = 'Market share by annual premium') AS reported_market_share_pct,
       MAX(f.value_num) FILTER (WHERE m.data_item = 'New business rate')              AS new_business_rate_pct,
       MAX(f.value_num) FILTER (WHERE m.data_item = 'Lapse rate')                     AS lapse_rate_pct
FROM fact_policy f
JOIN dim_measure m USING (measure_id)
WHERE m.subject = 'Policy Statistics'
  AND NOT f.is_invalid_combo
  AND NOT f.is_out_of_range
GROUP BY f.date_key, f.company_id, f.channel_id, f.cover_id;

-- ---------------------------------------------------------------------------------------------
-- Claims: outcomes, average sum insured, and the estimated average duration
-- has_outcomes is true only when received, finalised, admitted and declined are all visible,
-- so a rate built from this view never mixes a visible numerator with a hidden denominator
-- ---------------------------------------------------------------------------------------------
CREATE VIEW v_claims AS
SELECT f.date_key, f.company_id, f.channel_id, f.cover_id,
       MAX(f.value_num) FILTER (WHERE m.data_item = 'Number of claims' AND cat.category_name = 'Total Claims Received')        AS received,
       MAX(f.value_num) FILTER (WHERE m.data_item = 'Number of claims' AND cat.category_name = 'Finalised Claims')              AS finalised,
       MAX(f.value_num) FILTER (WHERE m.data_item = 'Number of claims' AND cat.category_name = 'Finalised Claims - Admitted')   AS admitted,
       MAX(f.value_num) FILTER (WHERE m.data_item = 'Number of claims' AND cat.category_name = 'Finalised Claims - Declined')   AS declined,
       MAX(f.value_num) FILTER (WHERE m.data_item = 'Number of claims' AND cat.category_name = 'Withdrawn Claims')              AS withdrawn,
       MAX(f.value_num) FILTER (WHERE m.data_item = 'Number of claims' AND cat.category_name = 'Undetermined Claims')           AS undetermined,
       MAX(f.value_num) FILTER (WHERE m.data_item = 'Average sum insured' AND cat.category_name = 'Finalised Claims - Admitted') AS avg_sum_insured_admitted,
       MAX(f.value_num) FILTER (WHERE m.data_item = 'Average sum insured' AND cat.category_name = 'Finalised Claims - Declined') AS avg_sum_insured_declined,
       MAX(f.value_num) FILTER (WHERE m.data_item = 'Total finalised claims')                                                   AS duration_finalised,
       MAX(f.value_num) FILTER (WHERE m.data_item = 'Est. average duration')                                                    AS est_avg_duration_months,
       (    MAX(f.value_num) FILTER (WHERE m.data_item = 'Number of claims' AND cat.category_name = 'Finalised Claims') IS NOT NULL
        AND MAX(f.value_num) FILTER (WHERE m.data_item = 'Number of claims' AND cat.category_name = 'Finalised Claims - Admitted') IS NOT NULL
        AND MAX(f.value_num) FILTER (WHERE m.data_item = 'Number of claims' AND cat.category_name = 'Finalised Claims - Declined') IS NOT NULL
       )                                                                                                                         AS has_outcomes
FROM fact_claims f
JOIN dim_measure  m   USING (measure_id)
JOIN dim_category cat USING (category_id)
WHERE m.subject IN ('Claims', 'Claims Duration')
  AND NOT f.is_invalid_combo
GROUP BY f.date_key, f.company_id, f.channel_id, f.cover_id;

-- ---------------------------------------------------------------------------------------------
-- Claims duration as one row per time band, so the bands can be stacked in a chart
-- the source gives each band as a percentage of finalised claims, est_claims turns that back into
-- an approximate count (the percentages are rounded) so that bands can be added across insurers and covers
-- ---------------------------------------------------------------------------------------------
CREATE VIEW v_claims_duration AS
WITH w AS (
    SELECT f.date_key, f.company_id, f.channel_id, f.cover_id,
           MAX(f.value_num) FILTER (WHERE m.data_item = 'Total finalised claims')    AS finalised_claims,
           MAX(f.value_num) FILTER (WHERE m.data_item = '0-2 weeks')                 AS b1,
           MAX(f.value_num) FILTER (WHERE m.data_item = '> 2 weeks to 2 months')     AS b2,
           MAX(f.value_num) FILTER (WHERE m.data_item = '> 2 months to 6 months')    AS b3,
           MAX(f.value_num) FILTER (WHERE m.data_item = '> 6 months to 12 months')   AS b4,
           MAX(f.value_num) FILTER (WHERE m.data_item = '> 12 months')               AS b5
    FROM fact_claims f
    JOIN dim_measure m USING (measure_id)
    WHERE m.subject = 'Claims Duration' AND NOT f.is_invalid_combo
    GROUP BY f.date_key, f.company_id, f.channel_id, f.cover_id
)
SELECT w.date_key, w.company_id, w.channel_id, w.cover_id, w.finalised_claims,
       b.band_order, b.band, b.band_pct,
       ROUND(w.finalised_claims * b.band_pct / 100.0) AS est_claims
FROM w
CROSS JOIN LATERAL (VALUES (1, '0-2 weeks',             w.b1),
                           (2, '2 weeks to 2 months',   w.b2),
                           (3, '2 to 6 months',         w.b3),
                           (4, '6 to 12 months',        w.b4),
                           (5, 'Over 12 months',        w.b5)) AS b(band_order, band, band_pct);

-- ---------------------------------------------------------------------------------------------
-- Disputes: outcomes, the lodgement ratio, average amount paid and duration
-- ---------------------------------------------------------------------------------------------
CREATE VIEW v_disputes AS
SELECT f.date_key, f.company_id, f.channel_id, f.cover_id,
       MAX(f.value_num) FILTER (WHERE m.data_item = 'Number of disputes' AND cat.category_name = 'Disputes Lodged')              AS lodged,
       MAX(f.value_num) FILTER (WHERE m.data_item = 'Number of disputes' AND cat.category_name = 'Disputes Resolved')            AS resolved,
       MAX(f.value_num) FILTER (WHERE m.data_item = 'Number of disputes' AND cat.category_name = 'Disputes Withdrawn')           AS withdrawn,
       MAX(f.value_num) FILTER (WHERE m.data_item = 'Number of disputes' AND cat.category_name = 'Disputes Undetermined')        AS undetermined,
       MAX(f.value_num) FILTER (WHERE m.data_item = 'Number of disputes' AND cat.category_name = 'Original decision maintained') AS maintained,
       MAX(f.value_num) FILTER (WHERE m.data_item = 'Number of disputes' AND cat.category_name = 'Original decision reversed')   AS reversed,
       MAX(f.value_num) FILTER (WHERE m.data_item = 'Number of disputes' AND cat.category_name = 'Other dispute outcomes')       AS other_outcomes,
       -- a rate per 100,000 lives insured, so it cannot be added across rows
       MAX(f.value_num) FILTER (WHERE m.data_item = 'Number of disputes per 100,000 lives insured')                              AS lodged_per_100k_lives,
       -- lives insured at the reporting date for the same company, channel, cover and date (from the policy sheet)
       -- lets Power BI build the per-100k ratio from rows where both numbers are visible
       MAX(pl.lives_insured)                                                                                                     AS lives_insured,
       MAX(f.value_num) FILTER (WHERE m.data_item = 'Average amount paid' AND cat.category_name = 'Disputes Resolved')            AS avg_amount_paid_resolved,
       MAX(f.value_num) FILTER (WHERE m.subject = 'Disputes Duration' AND m.data_item = 'Total disputes resolved')               AS duration_resolved,
       MAX(f.value_num) FILTER (WHERE m.subject = 'Disputes Duration' AND m.data_item = 'Est. average duration')                 AS est_avg_duration_months,
       (    MAX(f.value_num) FILTER (WHERE m.data_item = 'Number of disputes' AND cat.category_name = 'Disputes Resolved') IS NOT NULL
        AND MAX(f.value_num) FILTER (WHERE m.data_item = 'Number of disputes' AND cat.category_name = 'Original decision maintained') IS NOT NULL
        AND MAX(f.value_num) FILTER (WHERE m.data_item = 'Number of disputes' AND cat.category_name = 'Original decision reversed') IS NOT NULL
        AND MAX(f.value_num) FILTER (WHERE m.data_item = 'Number of disputes' AND cat.category_name = 'Other dispute outcomes') IS NOT NULL
       )                                                                                                                         AS has_outcomes
FROM fact_disputes f
JOIN dim_measure  m   USING (measure_id)
JOIN dim_category cat USING (category_id)
-- one 'Lives insured' row exists per company, channel, cover and date, so this join adds no extra rows
LEFT JOIN (SELECT fp.date_key, fp.company_id, fp.channel_id, fp.cover_id, fp.value_num AS lives_insured
           FROM fact_policy fp
           JOIN dim_measure pm USING (measure_id)
           WHERE pm.data_item = 'Lives insured') pl
       ON pl.date_key = f.date_key AND pl.company_id = f.company_id
      AND pl.channel_id = f.channel_id AND pl.cover_id = f.cover_id
WHERE m.subject IN ('Disputes', 'Disputes Duration')
  AND NOT f.is_invalid_combo
GROUP BY f.date_key, f.company_id, f.channel_id, f.cover_id;

-- ---------------------------------------------------------------------------------------------
-- Other sheet, reasons: why claims are declined or withdrawn, why disputes are withdrawn or reversed
-- industry-level, so there is no company
-- the same reason name can appear under more than one reason_group, so always filter on reason_group
-- the 'Total' reason (is_total_category) contains the others, never add it to them
-- ---------------------------------------------------------------------------------------------
CREATE VIEW v_industry_reasons AS
SELECT f.date_key, f.channel_id, f.cover_id,
       m.subject       AS reason_group,
       cat.category_name AS reason,
       cat.is_total_category,
       MAX(f.value_num) FILTER (WHERE m.data_item = 'Number of reasons') AS reason_count,
       MAX(f.value_num) FILTER (WHERE m.data_item = 'Percentage')        AS reason_pct
FROM fact_industry f
JOIN dim_measure  m   USING (measure_id)
JOIN dim_category cat USING (category_id)
WHERE m.subject <> 'Claims Ratio'
  AND NOT f.is_invalid_combo
GROUP BY f.date_key, f.channel_id, f.cover_id, m.subject, cat.category_name, cat.is_total_category;

-- ---------------------------------------------------------------------------------------------
-- Other sheet, claims ratios: claims frequency and claims paid ratio (both rates, never add them)
-- the 'Total' channel here covers all four channels together
-- ---------------------------------------------------------------------------------------------
CREATE VIEW v_industry_ratios AS
SELECT f.date_key, f.channel_id, f.cover_id,
       MAX(f.value_num) FILTER (WHERE m.data_item = 'Claims frequency')  AS claims_frequency_pct,
       MAX(f.value_num) FILTER (WHERE m.data_item = 'Claims paid ratio') AS claims_paid_ratio_pct
FROM fact_industry f
JOIN dim_measure m USING (measure_id)
WHERE m.subject = 'Claims Ratio'
  AND NOT f.is_invalid_combo
GROUP BY f.date_key, f.channel_id, f.cover_id;

-- ---------------------------------------------------------------------------------------------
-- Masking coverage for the data quality page: how many values APRA hid, per company, date, channel and cover
-- ---------------------------------------------------------------------------------------------
CREATE VIEW v_masking AS
SELECT 'Claims' AS sheet, f.date_key, f.company_id, f.channel_id, f.cover_id,
       COUNT(*) AS total_rows,
       COUNT(*) FILTER (WHERE f.value_status = 'masked') AS masked_rows
FROM fact_claims f
WHERE NOT f.is_invalid_combo
GROUP BY f.date_key, f.company_id, f.channel_id, f.cover_id
UNION ALL
SELECT 'Disputes', f.date_key, f.company_id, f.channel_id, f.cover_id,
       COUNT(*),
       COUNT(*) FILTER (WHERE f.value_status = 'masked')
FROM fact_disputes f
WHERE NOT f.is_invalid_combo
GROUP BY f.date_key, f.company_id, f.channel_id, f.cover_id;