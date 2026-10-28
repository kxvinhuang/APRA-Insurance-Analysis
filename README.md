# Australian Life Insurance Claims & Disputes Analytics

A data validation and cleaning project built on APRA's public life insurance claims and disputes statistics (June 2018 to June 2026), covering **all authorised life insurers**.

> **Status: work in progress** (last updated 28 Oct 2026). The inspection, validation, cleaning and database load and check stages are done.

## Project status

| Stage | Status | Files |
|---|---|---|
| Inspect raw data | Done | `src/inspect_data.py` |
| Validate raw data | Done | `src/validate_data.py`, `docs/data_validation.md` |
| Investigate data quirks | Done | `src/inspect_duration_conflicts.py`, `src/inspect_disputes_spelling.py` |
| Clean to tidy CSVs | Done | `src/clean_data.py`, `docs/cleaning_log.txt` |
| Load to PostgreSQL | Done | `src/load_to_sql.py`, `sql/schema.sql`, `sql/load.sql` |
| Check the database against the reports | Done | `sql/checks.sql` |

## The data

Source: APRA, *Life Insurance Claims and Disputes Statistics* (released half-yearly), with the explanatory notes and glossary. The workbook has four sheets used in this project:

| Sheet | Rows | What it holds |
|---|---|---|
| Policy Statistics | 23,797 | Lives insured, annual premium, market share, sum insured, new business and lapse rates |
| Claims | 95,261 | Claim counts by outcome (received, finalised, admitted, declined, withdrawn, undetermined), average sum insured, and claim duration |
| Disputes | 78,307 | Dispute counts and outcomes, average amount paid, and dispute duration |
| Other | 19,198 | **Industry-level only** (no company): claims frequency, claims paid ratio, and the reasons claims are declined or withdrawn and disputes are withdrawn or reversed |

Coverage: 17 reporting dates (30 June and 31 December each year), 20 ABNs (23 company names) plus an industry "Total", seven cover types (Death, TPD, Trauma, DII, CCI, Funeral, Accident) and four channels (Individual Advised, Individual Non-Advised, Group Super, Group Ordinary).

Every figure is a **rolling 12-month window** ending on the reporting date, so consecutive dates overlap by six months.

**Data version.** This repository includes the APRA release covering June 2018 to June 2026, and all numbers in this README describe that file (row counts, Excel row numbers, and the findings below). APRA can revise earlier figures in later releases, so a newer download may not match.

## Design principles

These follow from how the data is built, and they drive the cleaning rules.

- **Masked, missing and zero are three different things.** APRA masks a value with `*` when an insurer has fewer than 50 finalised claims. Masked values become NULL with a `value_status` flag, never zero.
- **Never sum across reporting dates.** The 12-month windows overlap. Use one date per year for annual totals, or treat each date as its own observation.
- **Never add a total to its parts.** The industry "Total" company, the "Total" channel and the "Total" reason category all contain the rows around them. They are flagged so charts can't double count.
- **Ratios can't be summed.** Aggregate the counts first, then recompute the ratio.
- **Flag, don't delete.** Rows that look wrong are kept with a flag (`is_invalid_combo`, `is_out_of_range`), and every dropped row is written to an exceptions file.

## Data quality findings

Found by `validate_data.py` and follow-up investigation. The latest validation run gave **65 passed, 4 warnings and 0 failures** (full results in `docs/data_validation.md`). The four warnings are the negative values in finding 8, the invalid combinations in finding 7 (one warning each for Claims and Disputes) and the capitalisation variants in finding 4 (Disputes). The duration conflict in finding 5 is reported as an explained, known quirk.

1. **Heavy masking.** About 42% of Claims values (40,075 rows) and 42% of Disputes values (32,696 rows) are masked. Claims masking ranges from 2% to about 78% depending on the insurer, so insurer-level claims metrics need to show how much of the data is hidden.
2. **"Total" is a company.** Each of the three company sheets has an industry "Total" company with a blank ABN (2,124 / 8,520 / 7,004 rows; the cell holds a single space, which cleaning converts to NULL). Where every value is visible, the sum of the insurers matches the Total for lives insured and annual premium (354 groups tested for each, no differences above 0.1%).
3. **Three ABNs changed name**: TAL Life Insurance Services (formerly Westpac Life Insurance Services), ART Life Insurance (formerly QInsure) and Nippon Life Insurance Australia and New Zealand (formerly MLC Limited). Companies are keyed on ABN, and name history is kept.
4. **Inconsistent capitalisation in Disputes**, for example "Disputes lodged" and "Disputes Lodged". Left uncorrected, this silently halved the number of groups a reconciliation could test, so names are normalised during cleaning.
5. **Contradictory duplicates.** Claims has 6 groups of exact duplicate rows (12 rows) and 10 groups (20 rows) where "Est. average duration" is published twice, once as 0 and once blank. Disputes has 3 groups of exact duplicates (6 rows). Inspecting each of the 10 groups showed that all have zero finalised claims, so the average is undefined. The validation step reports these as a known quirk, and the cleaning step keeps the blank, drops the 0, and logs the dropped rows. Any other conflicting duplicate stops the script. The cleaning run confirmed the drops: 6 exact duplicates and 10 zero-valued twins from Claims, and 3 exact duplicates from Disputes.
6. **Blank text in the Value column.** 10 Claims rows hold only spaces. They are treated as missing.
7. **Combinations APRA says can't exist.** APRA's notes list CCI × Group Super as not applicable, but the data has a block of rows for it under the industry Total only (24 rows in Claims, 20 in Disputes, 18 of each holding values). These are flagged and excluded from benchmarks.
8. **Negative lapse rates.** Three Policy Statistics values are negative (Excel rows 16099, 17731 and 23779), which the lapse rate definition (lapsed premium divided by average in-force premium) doesn't allow. They are flagged, not changed. Rates above 100% for lapse, new business and claims paid ratio are accepted as plausible.
9. **The Other sheet is a full grid**: 4,080 rows sit in invalid cover/channel combinations and all are blank.

Checks that passed:
- Claims and disputes reconciliations: received = finalised + withdrawn + undetermined, finalised = admitted + declined, lodged = resolved + withdrawn + undetermined, and resolved = maintained + reversed + other. Each was tested on 2,298 groups with no failures.
- On the Other sheet, reasons add up to the reported Total (2,704 groups, no failures).
- All reporting dates are valid 30 June / 31 December dates.
- No insurer name maps to more than one ABN.
- Every data item has exactly one unit and one calculation basis.
- The Notes column is only filled in on masked rows.
- No required column has a blank cell.

## Cleaning results

`clean_data.py` writes `policy_stats.csv`, `claims.csv`, `disputes.csv`, `industry_stats.csv` (the Other sheet), `company_names.csv` and `exceptions_dropped_duplicates.csv` to `data/processed/` (not committed), and logs the run to `docs/cleaning_log.txt`.

| Sheet | Rows read | Exact duplicates dropped | Zero-vs-blank twins dropped | Rows kept |
|---|---|---|---|---|
| Policy Statistics | 23,797 | 0 | 0 | 23,797 |
| Claims | 95,261 | 6 | 10 | 95,245 |
| Disputes | 78,307 | 3 | 0 | 78,304 |
| Other | 19,198 | 0 | 0 | 19,198 |

Value status after cleaning:

| Sheet | value | masked | missing |
|---|---|---|---|
| Policy Statistics | 23,795 | 2 | 0 |
| Claims | 53,783 | 40,075 | 1,387 |
| Disputes | 43,304 | 32,696 | 2,304 |
| Other | 13,758 | 1,024 | 4,416 |

Rows flagged and kept: 24 Claims and 20 Disputes rows with `is_invalid_combo` (the CCI × Group Super block from finding 7), 4,080 Other rows with `is_invalid_combo` (the blank grid from finding 9) and 3 Policy Statistics rows with `is_out_of_range` (the negative values from finding 8). `company_names.csv` holds 20 ABNs and 23 ABN/name pairs.

## Database

The cleaned CSVs are loaded into a PostgreSQL star schema. `sql/schema.sql` creates the tables, `src/load_to_sql.py` copies each CSV into a staging table, and `sql/load.sql` builds the dimensions and facts from staging. `sql/checks.sql` holds queries that re-derive numbers from the validation and cleaning reports (row counts, value status, flagged rows, industry Total against the sum of insurers, claims reconciliation, and masking by company).

| Type | Tables |
|---|---|
| Dimensions | `dim_date`, `dim_company` (with `company_name_history`), `dim_channel`, `dim_cover`, `dim_category`, `dim_measure` |
| Facts | `fact_policy`, `fact_claims`, `fact_disputes`, `fact_industry` (the Other sheet, so no company) |

Load results (every CSV row became exactly one row in its table):

| Table | CSV rows | Rows loaded |
|---|---|---|
| fact_policy | 23,797 | 23,797 |
| fact_claims | 95,245 | 95,245 |
| fact_disputes | 78,304 | 78,304 |
| fact_industry | 19,198 | 19,198 |
| company_name_history | 23 | 23 |

The dimensions hold 17 dates, 21 companies (20 insurers plus the industry Total), 5 channels (the four channels plus Total), 7 covers, 28 categories (27 plus a "no category" row) and 35 measures.

Design decisions:

- **Companies are keyed on ABN**, with a name history table, so a renamed insurer stays one company. The industry Total has no ABN.
- **A measure is a subject plus a data item.** The same reason name appears under both claims withdrawn reasons and dispute withdrawn reasons, so a category alone is not unique. Each measure has one unit and one calculation basis.
- **Rows with no category point to a "(none)" category** (id 0), so no fact key contains a NULL.
- **Masked and missing values are NULL with a `value_status`**, and constraints stop a masked or missing row from holding a number.
- **`is_additive` marks which measures can be summed** (counts and dollar totals, but not rates, averages or shares). This is my own classification and not something APRA publishes.
- **The Total flags live on the dimensions** (`is_industry_total`, `is_total_channel`, `is_total_category`), so one filter excludes them everywhere.
- **The load is one transaction.** It compares each table's row count with its CSV and rolls everything back if any count differs, so a failed load leaves the database as it was.

## Repository structure

```
APRA-Insurance-Analysis/
├── data/
│   ├── raw/             # APRA raw insurance data, release to June 2026
│   └── processed/       # tidy CSVs from clean_data.py (not committed)
├── src/
│   ├── inspect_data.py               # sheet names, shapes, previews, masked counts
│   ├── validate_data.py              # integrity checks -> docs/data_validation.md
│   ├── inspect_duration_conflicts.py # one-off investigation behind finding 5
│   ├── inspect_masking.py            # one-off inspection behind finding 1
│   ├── inspect_disputes_spelling.py  # one-off check behind finding 4
│   ├── clean_data.py                 # tidy, typed, flagged CSVs
│   └── load_to_sql.py                # loads the CSVs into PostgreSQL and checks row counts
├── sql/
│   ├── schema.sql                    # star schema and staging tables
│   ├── load.sql                      # builds dimensions and facts from staging
│   └── checks.sql                    # queries that re-derive numbers from the reports
├── docs/
│   ├── data_validation.md
│   ├── cleaning_log.txt
│   └── conflicting_duplicates_claims.csv
├── .env                 # database connection details (not committed)
├── .gitignore
├── requirements.txt
└── README.md
```

## How to run

1. Install dependencies: `pip install -r requirements.txt`
2. Create a PostgreSQL database (for example `CREATE DATABASE insurance_analytics;`) and add a `.env` file in the project root:

```
PGHOST=localhost
PGPORT=5432
PGDATABASE=insurance_analytics
PGUSER=postgres
PGPASSWORD=your_password
```

3. Run each stage from the project root:

```
python src/inspect_data.py
python src/validate_data.py     # writes docs/data_validation.md
python src/clean_data.py        # writes data/processed/*.csv and docs/cleaning_log.txt
python src/load_to_sql.py       # builds the tables in PostgreSQL and checks the row counts
```

Then run `sql/checks.sql` in pgAdmin or psql to compare the database with the validation and cleaning reports.

## Limitations

- Masking hides most small-insurer claims and disputes data, so insurer-level comparisons are only possible where values are visible.
- The Other sheet has no company dimension, so reasons and ratios are market-wide only.
- Insurers that left or were renamed are separate entries in time, so market trends partly reflect entries and exits.
- The glossary lists seven duration buckets, but the file has five for claims and three for disputes, so average duration is taken as reported and not recomputed.
- Findings apply to this release only.

## Tech

Python (pandas, numpy, psycopg2) and PostgreSQL.

## Data source and disclaimer

Data: Australian Prudential Regulation Authority (APRA), [*Life Insurance Claims and Disputes Statistics*](https://www.apra.gov.au/news-and-publications/life-insurance-claims-and-disputes-statistics). This project is independent and not affiliated with or endorsed by APRA.