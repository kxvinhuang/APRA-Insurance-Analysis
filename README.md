# Australian Life Insurance Claims & Disputes Analytics

A data validation and cleaning project built on APRA's public life insurance claims and disputes statistics (June 2018 to June 2026), covering **all authorised life insurers**.

> **Status: work in progress** (last updated 25 Oct 2026). The inspection and validation stages are done. Cleaning is in progress.

## Project status

| Stage | Status | Files |
|---|---|---|
| Inspect raw data | Done | `src/inspect_data.py` |
| Validate raw data | Done | `src/validate_data.py`, `docs/data_validation.md` |
| Investigate data quirks | Done | `src/inspect_duration_conflicts.py` |
| Clean to tidy CSVs | In progress | `src/clean_data.py` |

## The data

Source: APRA, *Life Insurance Claims and Disputes Statistics* (released half-yearly), with the explanatory notes and glossary. The workbook has four sheets used in this project:

| Sheet | Rows | What it holds |
|---|---|---|
| Policy Statistics | 23,797 | Lives insured, annual premium, market share, sum insured, new business and lapse rates |
| Claims | 95,261 | Claim counts by outcome (received, finalised, admitted, declined, withdrawn, undetermined), average sum insured, and claim duration |
| Disputes | 78,307 | Dispute counts and outcomes, average amount paid, and dispute duration |
| Other | 19,198 | **Industry-level only** (no company): claims frequency, claims paid ratio, and the reasons claims are declined or withdrawn and disputes are withdrawn or reversed |

Coverage: 17 reporting dates (30 June and 31 December each year), 21 ABNs (24 company names) plus an industry "Total", seven cover types (Death, TPD, Trauma, DII, CCI, Funeral, Accident) and four channels (Individual Advised, Individual Non-Advised, Group Super, Group Ordinary).

Every figure is a **rolling 12-month window** ending on the reporting date, so consecutive dates overlap by six months.

## Design principles

These follow from how the data is built, and they drive the cleaning rules.

- **Masked, missing and zero are three different things.** APRA masks a value with `*` when an insurer has fewer than 50 finalised claims. Masked values become NULL with a `value_status` flag, never zero.
- **Never sum across reporting dates.** The 12-month windows overlap. Use one date per year for annual totals, or treat each date as its own observation.
- **Never add a total to its parts.** The industry "Total" company, the "Total" channel and the "Total" reason category all contain the rows around them. They are flagged so charts can't double count.
- **Ratios can't be summed.** Aggregate the counts first, then recompute the ratio.
- **Flag, don't delete.** Rows that look wrong are kept with a flag (`is_invalid_combo`, `is_out_of_range`), and every dropped row is written to an exceptions file.

## Data quality findings

Found by `validate_data.py` and follow-up investigation. The latest validation run gave **46 passed, 3 warnings and 0 failures** (full results in `docs/data_validation.md`). The three warnings are the negative values in finding 8 and the invalid combinations in finding 7 (one warning each for Claims and Disputes). The duration conflict in finding 5 is reported as an explained, known quirk.

1. **Heavy masking.** About 42% of Claims values (40,075 rows) and 42% of Disputes values (32,696 rows) are masked. Claims masking ranges from 0% to about 78% depending on the insurer, so insurer-level claims metrics need to show how much of the data is hidden.
2. **"Total" is a company.** Each of the three company sheets has an industry "Total" company with no ABN (2,124 / 8,520 / 7,004 rows). Where every value is visible, the sum of the insurers matches the Total for lives insured and annual premium (354 groups tested for each, no differences above 0.1%).
3. **Three ABNs changed name**: TAL Life Insurance Services (formerly Westpac Life Insurance Services), ART Life Insurance (formerly QInsure) and Nippon Life Insurance Australia and New Zealand (formerly MLC Limited). Companies are keyed on ABN, and name history is kept.
4. **Inconsistent capitalisation in Disputes**, for example "Disputes lodged" and "Disputes Lodged". Left uncorrected, this silently halved the number of groups a reconciliation could test, so names are normalised during cleaning.
5. **Contradictory duplicates.** Claims has 6 groups of exact duplicate rows (12 rows) and 10 groups (20 rows) where "Est. average duration" is published twice, once as 0 and once blank. Disputes has 3 groups of exact duplicates (6 rows). Inspecting each of the 10 groups showed that all have zero finalised claims, so the average is undefined. The validation step reports these as a known quirk, and the cleaning step keeps the blank, drops the 0, and logs the dropped rows. Any other conflicting duplicate stops the script.
6. **Blank text in the Value column.** 10 Claims rows hold only spaces. They are treated as missing.
7. **Combinations APRA says can't exist.** APRA's notes list CCI × Group Super as not applicable, but the data has a block of rows for it under the industry Total only (24 rows in Claims, 20 in Disputes, 18 of each holding values). These are flagged and excluded from benchmarks.
8. **Negative lapse rates.** Three Policy Statistics values are negative (Excel rows 16099, 17731 and 23779), which the lapse rate definition (lapsed premium divided by average in-force premium) doesn't allow. They are flagged, not changed. Rates above 100% for lapse, new business and claims paid ratio are accepted as plausible.
9. **The Other sheet is a full grid**: 4,080 rows sit in invalid cover/channel combinations and all are blank.

Checks that passed:
- Claims and disputes reconciliations: received = finalised + withdrawn + undetermined, finalised = admitted + declined, lodged = resolved + withdrawn + undetermined, and resolved = maintained + reversed + other. Each was tested on 2,298 groups with no failures.
- On the Other sheet, reasons add up to the reported Total (2,704 groups, no failures).
- All reporting dates are valid 30 June / 31 December dates.
- No insurer name maps to more than one ABN.

## Repository structure

```
insurance-analytics/
├── data/
│   ├── raw/             # APRA workbook (not committed)
│   └── processed/       # tidy CSVs from clean_data.py (not committed)
├── src/
│   ├── inspect_data.py               # sheet names, shapes, previews, masked counts
│   ├── validate_data.py              # integrity checks -> docs/data_validation.md
│   ├── inspect_duration_conflicts.py # one-off investigation behind finding 5
│   └── clean_data.py                 # tidy, typed, flagged CSVs
├── docs/
│   ├── data_validation.md
│   └── conflicting_duplicates_claims.csv
├── .gitignore
├── requirements.txt
└── README.md
```

## How to run

1. Download the APRA workbook and save it in `data/raw/` with the file name used in the scripts.
2. Install dependencies: `pip install pandas numpy openpyxl`
3. Run each stage from the project root:

```
python src/inspect_data.py
python src/validate_data.py     # writes docs/data_validation.md
python src/clean_data.py        # writes data/processed/*.csv and docs/cleaning_log.txt
```

## Limitations

- Masking hides most small-insurer claims and disputes data, so insurer-level comparisons are only possible where values are visible.
- The Other sheet has no company dimension, so reasons and ratios are market-wide only.
- Insurers that left or were renamed are separate entries in time, so market trends partly reflect entries and exits.
- The glossary lists seven duration buckets, but the file has five for claims and three for disputes, so average duration is taken as reported and not recomputed.

## Tech

Python (pandas, numpy).

## Data source and disclaimer

Data: Australian Prudential Regulation Authority (APRA), *Life Insurance Claims and Disputes Statistics*. This project is independent and not affiliated with or endorsed by APRA.