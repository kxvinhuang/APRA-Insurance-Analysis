from pathlib import Path
import numpy as np
import pandas as pd

FILE = Path("data/raw/Life insurance claims and disputes statistics database June 2018 to June 2026.xlsx")
OUT = Path("data/processed")
LOG = Path("docs/cleaning_log.txt")

# each raw sheet and the name of the csv it becomes
SHEETS = {"Policy Statistics": "policy_stats", "Claims": "claims",
          "Disputes": "disputes", "Other": "industry_stats"}
RENAME = {
    "Reporting Date": "reporting_date", "Company Name": "company_name", "ABN": "abn",
    "Subject": "subject", "Channel Type": "channel_type", "Cover Type": "cover_type",
    "Category": "category", "Data item": "data_item", "Calculation Basis": "calculation_basis",
    "Value": "value_raw", "Unit": "unit", "Notes": "notes",
}
TEXT_COLS = ["company_name", "abn", "subject", "channel_type", "cover_type", "category",
             "data_item", "calculation_basis", "unit", "notes"]

# the Disputes sheet spells some category names two ways shown by running inspect_disputes_spelling.py
# the keys are the lower case versions and the values are the one spelling we keep
CANON = {
    "average amount paid": "Average amount paid",
    "total disputes resolved": "Total disputes resolved",
    "disputes lodged": "Disputes Lodged",
    "disputes resolved": "Disputes Resolved",
    "disputes withdrawn": "Disputes Withdrawn",
    "disputes undetermined": "Disputes Undetermined",
    # this item is also used for claims reasons, so 'dispute' in the name was misleading
    "number of dispute reasons": "Number of reasons",
}

CHANNELS = {"Individual Advised", "Individual Non-Advised", "Group Super", "Group Ordinary"}
# cover/channel combinations APRA says can be reported
VALID_COMBOS = {
    "Death": CHANNELS, "TPD": CHANNELS, "Trauma": CHANNELS, "DII": CHANNELS,
    "CCI": {"Individual Non-Advised", "Group Ordinary"},
    "Funeral": {"Individual Non-Advised"},
    "Accident": {"Individual Advised", "Individual Non-Advised", "Group Ordinary"},
}
# percentages above 100 are plausible for these items
RATE_ITEMS = {"Lapse rate", "New business rate", "Claims paid ratio"}
# cleaning is logged and kept here so it can be saved to the log file at the end
LINES = []


def log(text=""):
    print(text)
    LINES.append(str(text))


def clean_sheet(xls, sheet):
    df = pd.read_excel(xls, sheet_name=sheet, dtype={"ABN": str})
    df.columns = [str(c).strip() for c in df.columns]
    df = df.rename(columns=RENAME)

    # split the raw value into a number and a status, a value can be a number, a masked '*' or blank
    # pop removes value_raw from the table and gives it back as its own column stored as raw
    raw = df.pop("value_raw")
    # used to spot '*' and blank text
    text = raw.astype(str).str.strip()
    # true where the cell holds text rather than a number
    is_text = raw.map(lambda x: isinstance(x, str))
    # turns numbers into numeric values and anything else like '*' or ' ' into NaN
    num = pd.to_numeric(raw, errors="coerce")
    masked = is_text & text.eq("*")
    # missing means being null or only spaces so a cell with just ' ' counts as blank
    missing = raw.isna() | (is_text & text.eq(""))
    # any other text that is not a number, '*' or blank is unexpected, so stop instead of guessing
    if (is_text & ~masked & ~missing & num.isna()).any():
        raise ValueError(f"{sheet}: unexpected text in the Value column")
    # masked and missing values get no number, a masked value must never be turned into 0
    df["value_num"] = num.where(~masked & ~missing)
    # status says why a value has no number, 'value' means it has a real number
    df["value_status"] = np.select([masked, missing], ["masked", "missing"], default="value")

    # trim text, making empty cells NaN
    for c in TEXT_COLS:
        if c in df.columns:
            # map every row so if it is a string, it gets stripped and if its empty after,
            # its set to NaN. if its not a string, it gets set to NaN too
            df[c] = df[c].map(lambda x: (x.strip() or np.nan) if isinstance(x, str) else np.nan)
    df["reporting_date"] = pd.to_datetime(df["reporting_date"])
    # swap the different spellings of the same name for the single spelling in CANON
    # lower case is used for the lookup, and names that are not in CANON are left as they are
    for c in ("data_item", "category"):
        if c in df.columns:
            df[c] = df[c].map(lambda x: CANON.get(x.lower(), x) if isinstance(x, str) else x)

    # duplicates
    # key = every descriptive column, including Unit and Notes
    # will not include company or ABN for the Other sheet
    keys = ["reporting_date"] + [c for c in TEXT_COLS if c in df.columns]
    # merge all the key columns into a single string, replacing NaN with <blank> and joining each col
    # with "|" so that each row can be compared as a single string
    key = df[keys].astype(str).fillna("<blank>").agg("|".join, axis=1)
    # add the status and number to the key string
    with_value = key + "|" + df["value_status"] + "|" + df["value_num"].astype(str).fillna("<blank>")

    # when theres no finalised claims, 'Est. average duration' is reported twice,
    # once as 0 and once blank, an average over zero claims is undefined so we keep the blank row
    # clash is true for rows that share a key with another row but have a different value
    clash = key.duplicated(keep=False) & ~with_value.duplicated(keep=False)
    # the row of an 'Est. average duration' clash where value is 0
    zero_twin = clash & df["data_item"].eq("Est. average duration") & df["value_num"].eq(0)
    # only drop the 0 row if a blank row with the same key exists
    has_blank_twin = key.isin(key[df["value_status"].eq("missing")])
    quirk = zero_twin & has_blank_twin
    # keep a copy of the rows being dropped so they can be saved to the exceptions file
    quirk_rows = df[quirk].assign(sheet=sheet)
    # remove them from the table and from the key series so everything stays lined up
    df, key, with_value = df[~quirk], key[~quirk], with_value[~quirk]

    # any other rows that share a key but have different values are unexplained, so stop here
    if (key.duplicated(keep=False) & ~with_value.duplicated(keep=False)).any():
        raise ValueError(f"{sheet}: duplicate rows with different values - inspect before cleaning")
    # what is left are exact duplicates, keep="first" marks every copy except the first one
    dup = key.duplicated(keep="first")
    # everything dropped from this sheet, the 0 rows from above plus the extra exact copies
    dropped = pd.concat([quirk_rows, df[dup].assign(sheet=sheet)])
    # notes is dropped now that duplicates are done as it only repeats the masking message
    df = df[~dup].drop(columns=["notes"], errors="ignore")

    # flags, rows are flagged and kept rather than deleted
    # the Other sheet has no company column
    if "company_name" in df.columns:
        df["is_industry_total"] = df["company_name"].str.lower().eq("total")
    # true when the cover/channel combination is not allowed by APRA, a Total channel is never invalid
    df["is_invalid_combo"] = [ch != "Total" and ch not in VALID_COMBOS.get(cv, set())
                              for cv, ch in zip(df["cover_type"], df["channel_type"])]
    v = df["value_num"]
    # negative values that are not dollars, or percentages above 100 excluding the three rate items
    df["is_out_of_range"] = ((v < 0) & (df["unit"] != "$")) | \
                            ((df["unit"] == "%") & (v > 100) & ~df["data_item"].isin(RATE_ITEMS))
    # the Other sheet has a Total channel and a Total category that contain the rows around them
    # so they are flagged to stop them being added up with the rest
    if sheet == "Other":
        df["is_total_channel"] = df["channel_type"].eq("Total")
        df["is_total_category"] = df["category"].str.lower().eq("total")

    log(f"{sheet}: rows read={len(raw)}, exact duplicates dropped={int(dup.sum())}, "
        f"zero-vs-blank 'Est. average duration' twins dropped={len(quirk_rows)}, rows kept={len(df)}")
    log(f"    value_status: {df['value_status'].value_counts().to_dict()}")
    log(f"    flagged: invalid combo={int(df['is_invalid_combo'].sum())}, "
        f"out of range={int(df['is_out_of_range'].sum())}")
    return df, dropped


def main():
    # create the output folders if they do not exist, and do nothing if they do
    OUT.mkdir(parents=True, exist_ok=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    xls = pd.ExcelFile(FILE)
    frames, dropped = {}, []
    # clean each sheet, frames is keyed by output csv name and dropped collects the rows removed from each sheet
    for sheet, name in SHEETS.items():
        frames[name], d = clean_sheet(xls, sheet)
        dropped.append(d)

    # company name history, ABN is the stable key because company names change over time
    # stack the three company sheets and keep only real insurers (not the industry Total)
    comp = pd.concat([frames[n].loc[~frames[n]["is_industry_total"], ["abn", "company_name", "reporting_date"]]
                      for n in ("policy_stats", "claims", "disputes")])
    # for each ABN and name pair, the first and last date that name appears
    names = comp.groupby(["abn", "company_name"])["reporting_date"].agg(first_date="min", last_date="max").reset_index()
    # the latest name for an ABN is the pair whose last date is the latest for that ABN
    names["is_latest_name"] = names["last_date"].eq(names.groupby("abn")["last_date"].transform("max"))

    # write everything out, index=False leaves out pandas' own row numbers
    names.to_csv(OUT / "company_names.csv", index=False)
    pd.concat(dropped).to_csv(OUT / "exceptions_dropped_duplicates.csv", index=False)
    for name, df in frames.items():
        df.to_csv(OUT / f"{name}.csv", index=False)

    log(f"\ncompany_names.csv: {names['abn'].nunique()} ABNs, {len(names)} ABN/name pairs")
    log("Files written to " + str(OUT))
    # save the log, one logged line per line in the file
    LOG.write_text("\n".join(LINES), encoding="utf-8")


if __name__ == "__main__":
    main()