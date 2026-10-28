from pathlib import Path
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FILE = PROJECT_ROOT / "data/raw/Life insurance claims and disputes statistics database June 2018 to June 2026.xlsx"
REPORT = Path("docs/data_validation.md")

SHEETS = ["Policy Statistics", "Claims", "Disputes", "Other"]
RENAME = {
    "Reporting Date": "reporting_date", "Company Name": "company_name", "ABN": "abn",
    "Subject": "subject", "Channel Type": "channel_type", "Cover Type": "cover_type",
    "Category": "category", "Data item": "data_item", "Calculation Basis": "calculation_basis",
    "Value": "value_raw", "Unit": "unit", "Notes": "notes",
}
TEXT_COLS = ["company_name", "abn", "subject", "channel_type", "cover_type", "category",
             "data_item", "calculation_basis", "unit", "notes"]
REQUIRED = ["reporting_date", "subject", "channel_type", "cover_type", "data_item",
            "calculation_basis", "value_raw", "unit"]

CHANNELS = {"Individual Advised", "Individual Non-Advised", "Group Super", "Group Ordinary"}
COVERS = {"Death", "TPD", "Trauma", "DII", "CCI", "Funeral", "Accident"}
UNITS = {"%", "Number", "Months", "$"}
# cover/channel combinations APRA says can be reported
VALID_COMBOS = {
    "Death": CHANNELS, "TPD": CHANNELS, "Trauma": CHANNELS, "DII": CHANNELS,
    "CCI": {"Individual Non-Advised", "Group Ordinary"},
    "Funeral": {"Individual Non-Advised"},
    "Accident": {"Individual Advised", "Individual Non-Advised", "Group Ordinary"},
}
# Percentages above 100 are plausible for these items
RATE_ITEMS = {"Lapse rate", "New business rate", "Claims paid ratio"}
# (sheet, check, status, detail)
RESULTS = []


def record(sheet, name, status, detail=""):
    RESULTS.append((sheet, name, status, detail))
    print(f"[{status:<4}] {sheet} - {name}: {detail}")


def check(sheet, name, ok, detail="", warn=False):
    record(sheet, name, "PASS" if ok else ("WARN" if warn else "FAIL"), detail)


def load(xls, sheet):
    df = pd.read_excel(xls, sheet_name=sheet, dtype={"ABN": str})
    df.columns = [str(c).strip() for c in df.columns]
    df = df.rename(columns=RENAME)
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"{sheet}: missing columns {missing}")
    # add a column that tracks every row's original Excel row num
    df.insert(0, "excel_row", df.index + 2)

    # values can be a number, a masked '*', blank, or something unexpected
    raw = df["value_raw"]
    text = raw.astype(str).str.strip()
    is_text = raw.map(lambda x: isinstance(x, str))
    num = pd.to_numeric(raw, errors="coerce")
    df["status"] = np.select(
        [raw.isna(), is_text & text.eq("*"), is_text & text.eq(""), is_text & num.isna()],
        ["missing", "masked", "blank text", "other text"], default="value")
    df["num"] = num.where(df["status"] == "value")

    # trim text, making empty cells NaN
    for c in TEXT_COLS:
        if c in df.columns:
            # map every row so if it is a string, it gets stripped and if its empty after,
            # its set to NaN, if its not a string, it gets set to NaN
            df[c] = df[c].map(lambda x: (x.strip() or np.nan) if isinstance(x, str) else np.nan)
    df["reporting_date"] = pd.to_datetime(df["reporting_date"], errors="coerce")
    return df


def show_conflicts(df, k, conflict, sheet, max_groups=10):
    # every row that shares a key with a conflicting row, including the identical copies
    # k[conflict] holds the keys of the conflicting rows and k.isin() is true for every row
    # whose key is in that set, so this keeps the whole group and not just the odd one out
    rows = df[k.isin(k[conflict])]
    # keep only the descriptive columns this sheet has that identify a group
    ident = [c for c in ["reporting_date", "company_name", "channel_type", "cover_type",
                         "subject", "category", "data_item", "unit"] if c in df.columns]
    # counts the distinct conflicting keys, which is the number of groups
    print(f"\n  {sheet}: {k[conflict].nunique()} key groups contain conflicting values (showing up to {max_groups})")
    # groupby splits the rows into one group per key and each loop gives (key, group_table)
    # the key itself isn't needed so it goes into _ and g is the group's rows
    # k.loc[rows.index] picks the key for just these rows so it lines up with them
    # enumerate adds a counter i so the loop can stop after max_groups groups
    for i, (_, g) in enumerate(rows.groupby(k.loc[rows.index])):
        # stop once max_groups groups have been printed
        if i == max_groups:
            break
        # print the identifying fields once, taken from the first row of the group
        # as they are the same for every row in it, to_dict makes it readable on one line
        print("   ", g.iloc[0][ident].to_dict())
        # then a small table of just the columns that can differ between the rows
        # index=False hides pandas' own row numbers so only the Excel row shows
        print(g[["excel_row", "value_raw", "status", "num"]].to_string(index=False))
    # save every conflicting group so it can be opened in Excel
    out = REPORT.parent / f"conflicting_duplicates_{sheet.replace(' ', '_').lower()}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows.to_csv(out, index=False)
    print(f"   all {len(rows)} rows saved to {out}")


def sheet_checks(df, sheet):
    # 1. allowed values
    channels = CHANNELS | ({"Total"} if sheet == "Other" else set())
    for col, allowed in [("channel_type", channels), ("cover_type", COVERS), ("unit", UNITS)]:
        # get every distinct value with NaN removed, then minus allowed values to get unexpected values
        bad = sorted(set(df[col].dropna()) - allowed)
        # report unexpected categorical values as warnings so validation can continue.
        # the ok flag (not bad) is true when bad is empty
        check(sheet, f"allowed {col} values", not bad, f"unexpected: {bad}" if bad else "ok", warn=True)

    # 2. reporting dates
    d = df["reporting_date"]
    ok = ((d.dt.month == 6) & (d.dt.day == 30)) | ((d.dt.month == 12) & (d.dt.day == 31))
    # check all reporting dates are right and report how many unique dates from earliest to latest and ~ok flips conditions to check how many are invalid
    check(sheet, "reporting dates are 30 Jun / 31 Dec", ok.all(),
          f"{d.nunique()} dates from {d.min():%Y-%m-%d} to {d.max():%Y-%m-%d}; {int((~ok).sum())} invalid")

    # 3. duplicates
    # key = every descriptive column, including Unit and Notes
    # will not include company or ABN for the Other sheet
    keys = ["reporting_date"] + [c for c in TEXT_COLS if c in df.columns]
    # merge all the key columns into a single string, replacing NaN with <blank> and joining each col
    # with "|" so that each row can be compared as a single string
    k = df[keys].astype(str).fillna("<blank>").agg("|".join, axis=1)
    # add the status and num columns to the key string
    vk = k + "|" + df["status"] + "|" + df["num"].astype(str).fillna("<blank>")
    exact = vk.duplicated(keep=False)
    # checks if there are rows with same descriptive columns but different values
    conflict = k.duplicated(keep=False) & ~exact
    # with no finalised claims, 'Est. average duration' is reported twice, once as 0
    # and once blank. Cleaning keeps the blank, so it is reported as info instead of a failure
    twin = df["data_item"].eq("Est. average duration") & (df["num"].eq(0) | df["status"].eq("missing"))
    quirk = conflict & twin
    conflict = conflict & ~quirk
    record(sheet, "known quirk: 'Est. average duration' 0 vs blank twins", "INFO",
           f"{int(quirk.sum())} rows in {k[quirk].nunique()} groups (cleaning keeps the blank)")
    check(sheet, "no duplicate keys with different values", not conflict.any(), f"{int(conflict.sum())} rows")
    if conflict.any():
        show_conflicts(df, k, conflict, sheet)
    # record the number of exact duplicate rows, and how many unique groups theyre in
    record(sheet, "exact duplicate rows (cleaning drops the extra copy)", "INFO",
           f"{int(exact.sum())} rows in {vk[exact].nunique()} groups")

    # 4. value column
    counts = df["status"].value_counts().to_dict()
    record(sheet, "Value status", "INFO", str(counts))
    check(sheet, "no unrecognised text in Value", counts.get("other text", 0) == 0,
          f"{counts.get('other text', 0)} rows")

    # 5. company / ABN (not on the Other sheet)
    if "company_name" in df.columns:
        total = df["company_name"].str.lower().eq("total")
        bad_abn = ~df["abn"].fillna("").str.fullmatch(r"\d{11}")
        check(sheet, "every non-Total row has an 11-digit ABN", not (bad_abn & ~total).any(),
              f"{int((bad_abn & ~total).sum())} rows")
        record(sheet, "industry 'Total' company rows", "INFO", f"{int(total.sum())} rows")
        # get all abn and company name pairs where row isn't industry total
        pairs = df.loc[~total, ["abn", "company_name"]].drop_duplicates()
        # group by company name and check the number of unique ABNs for each company name
        # should be 1, otherwise check fails
        check(sheet, "each company name has one ABN",
              not (pairs.groupby("company_name")["abn"].nunique() > 1).any())
        # keeps the ABNs that have more than one company name, meaning theyve been renamed
        renamed = pairs.groupby("abn").filter(lambda g: len(g) > 1)
        # report number of ABNs that have been renamed along with company names theyve been
        # renamed to sorted alphabetically and joined with semicolon
        record(sheet, "ABNs with more than one name (renames)", "INFO",
               f"{renamed['abn'].nunique()} ABNs: " + "; ".join(sorted(renamed["company_name"])))

    # 6. cover/channel combinations
    bad = np.array([ch != "Total" and ch not in VALID_COMBOS.get(cv, set())
                    for cv, ch in zip(df["cover_type"], df["channel_type"])])
    # holds the invalid combo rows
    inv = df[bad]
    with_data = int((inv["status"] != "missing").sum())
    if "company_name" in df.columns:
        # count num of industry total rows in invalid rows
        n_total = int(inv["company_name"].str.lower().eq("total").sum())
        # separate invalid combinations reported for the industry total from insurer rows.
        check(sheet, "cover/channel combinations allowed by APRA", inv.empty,
              f"{len(inv)} rows ({n_total} under Total company, {with_data} with a value or mask)", warn=True)
    else:
        # check if any invalid combination rows contain data, its acceptable if data is missing, but warns
        # if there is data in invalid rows
        check(sheet, "cover/channel combinations allowed by APRA", with_data == 0,
              f"{len(inv)} grid rows, {with_data} with a value or mask", warn=True)

    # 7. ranges
    v = df["num"]
    neg = (v < 0) & (df["unit"] != "$")
    # a percentage above 100% excluding lapse rate, new business rate and claims paid ratio
    over = (df["unit"] == "%") & (v > 100) & ~df["data_item"].isin(RATE_ITEMS)
    # if there are neg values, shows first five excel row numbers for neg value rows
    check(sheet, "no negative values (except $)", not neg.any(),
          f"{int(neg.sum())} rows, Excel rows {df.loc[neg, 'excel_row'].head(5).tolist()}", warn=True)
    # same but for percentages above 100% excluding the three rate items
    check(sheet, "no % above 100 (except rate/ratio items)", not over.any(),
          f"{int(over.sum())} rows, Excel rows {df.loc[over, 'excel_row'].head(5).tolist()}", warn=True)

    # 8. spelling variants, the same name written with different capitalisation or spacing
    found = {}
    for col in ["company_name", "subject", "channel_type", "cover_type", "category", "data_item",
                "calculation_basis", "unit"]:
        if col in df.columns:
            # distinct values with NaN removed
            vals = pd.Series(df[col].dropna().unique(), dtype=object)
            # lower case with sequential spaces collapsed, so spellings of one name end up identical
            norm = vals.str.lower().str.replace(r"\s+", " ", regex=True)
            # keep the values whose normalised form appears more than once
            variants = vals[norm.duplicated(keep=False)].sort_values().tolist()
            if variants:
                found[col] = variants
    check(sheet, "one spelling per name", not found, str(found) if found else "ok", warn=True)

    # 9. each data item should always have the same unit and calculation basis
    # lower case the data item so the capitalisation variants are counted as one item
    item = df["data_item"].str.lower()
    for col in ["unit", "calculation_basis"]:
        # count the distinct units for each subject and data item
        n = df.groupby(["subject", item])[col].nunique()
        check(sheet, f"one {col} per data item", (n <= 1).all(),
              f"{int((n > 1).sum())} data items with more than one", warn=True)

    # 10. the notes column only has a value on masked rows stating it has been masked as sample size 
    # is too small to be statistically credible, allowing it to be dropped later
    if "notes" in df.columns:
        stray = df["notes"].notna() & (df["status"] != "masked")
        check(sheet, "Notes only on masked rows", not stray.any(), f"{int(stray.sum())} rows")

    # 11. columns that must never be blank, the database will not allow nulls in them
    required = [c for c in REQUIRED if c != "value_raw" and c in df.columns]
    if "company_name" in df.columns:
        required.append("company_name")
    blank = df[required].isna().sum()
    blank = blank[blank > 0]
    check(sheet, "no blanks in required columns", blank.empty, str(blank.to_dict()) if len(blank) else "ok")


def reconcile(df, sheet, subject, item, total, parts, label):
    # within each company/channel/cover/date, total category must equal the sum of its parts
    s = df[(df["subject"].str.lower() == subject) & (df["data_item"].str.lower() == item)].copy()
    s["cat"] = s["category"].str.lower()
    keys = ["reporting_date", "company_name", "channel_type", "cover_type"]
    # group by the combination of keys and category and take the first non null value for each group
    # then unstack the category col so each distinct category becomes a separate column on the same
    # combination of keys
    wide = s.groupby(keys + ["cat"])["num"].first().unstack("cat")
    # needed categories are the total category and all the parts
    need = [total] + parts
    missing = [c for c in need if c not in wide.columns]
    # record a warning if any of the parts that make up total are missing, and return early as the check cannot be performed
    if missing:
        record(sheet, label, "WARN", f"categories not found: {missing}")
        return
    # keep only the rows where all needed categories are present, leaves out all masked or missing values
    testable = wide.dropna(subset=need)
    # subtracts the sum of the parts across columns from the total column, failed if not 0
    # failures are summed
    failed = int(((testable[total] - testable[parts].sum(axis=1)) != 0).sum())
    check(sheet, label, failed == 0, f"{len(testable)} testable groups (of {len(wide)}), {failed} failed")


def industry_totals(pol):
    # from policy stats sheet, the sum of the insurers should equal the industry 'Total' company for additive items
    # like lives insrued and annual premium
    total = pol["company_name"].str.lower().eq("total")
    keys = ["reporting_date", "channel_type", "cover_type"]
    for item in ["Lives insured", "Annual premium"]:
        d = pol[pol["data_item"] == item]
        if d.empty:
            record("Policy Statistics", f"Total = sum of insurers ({item})", "WARN", "no rows found")
            continue
        # checks if every unique group of keys has all rows with actual values
        all_ok = d.groupby(keys)["status"].agg(lambda s: bool((s == "value").all()))
        # sums the values for insurers <item> values for each group of keys
        insurers = d[~total.loc[d.index]].groupby(keys)["num"].sum()
        # gets the reported total for each group of keys
        reported = d[total.loc[d.index]].groupby(keys)["num"].first()
        # places the three results side by side, drops any groups that have missing values for any of the three columns
        g = pd.concat([insurers.rename("insurers"), reported.rename("total"), all_ok.rename("ok")], axis=1).dropna()
        # only keeps groups where every contributing row contains an actual value
        g = g[g["ok"]]
        # get relative difference between of the gap as a fraction of reported total
        # uses replace to avoid dividing by 0
        rel = (g["insurers"] - g["total"]).abs() / g["total"].replace(0, np.nan)
        # anything above 0.1% is considered a fail, num of fails is summed
        bad = int((rel > 0.001).sum())
        check("Policy Statistics", f"Total = sum of insurers ({item})", bad == 0,
              f"{len(g)} groups tested, {bad} differ by more than 0.1%")


def reason_sums(o):
    # on the Other sheet, reasons should add up to the reported 'Total' category
    # keep only the rows where category is not null
    o = o[o["category"].notna()]
    is_total = o["category"].str.lower().eq("total")
    keys = ["reporting_date", "subject", "channel_type", "cover_type", "data_item", "unit"]
    # for each unique group of keys for non-total category rows, sum all num values if all are actual values
    parts = o[~is_total].groupby(keys)["num"].agg(lambda s: s.sum() if s.notna().all() else np.nan)
    # get reported total for the unique grou of keys
    total = o[is_total].groupby(keys)["num"].first()
    # place them side by side, drop any groups that have missing values for either col
    g = pd.concat([parts.rename("parts"), total.rename("total")], axis=1).dropna()
    # set tolerance for % totals to 1.0, 0 otherwise
    tol = np.where(g.index.get_level_values("unit") == "%", 1.0, 0.0)
    # percentage totals allow a one-point rounding difference and other units require an exact match.
    failed = int(((g["parts"] - g["total"]).abs() > tol).sum())
    check("Other", "reasons add up to Total category", failed == 0, f"{len(g)} groups tested, {failed} failed")


def write_report():
    # builds a sum for each different status
    n = {s: sum(1 for r in RESULTS if r[2] == s) for s in ["PASS", "WARN", "FAIL", "INFO"]}
    # header of validation report 
    lines = ["# Data Validation Report", "",
             f"Source: `{FILE.name}`", "", "Generated by `src/validate_data.py`.", "",
             f"**{n['PASS']} passed, {n['WARN']} warnings, {n['FAIL']} failed** ({n['INFO']} informational).", "",
             "| Sheet | Check | Status | Detail |", "|---|---|---|---|"]
    for sheet, name, status, detail in RESULTS:
        lines.append(f"| {sheet} | {name} | {status} | {str(detail).replace('|', '/')} |")
    # go to parent directory and make directory if doesnt exist, if exists, do nothing
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    # creates the report file and writes the lines into it separated by new lines
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n{n['PASS']} passed, {n['WARN']} warnings, {n['FAIL']} failed. Report: {REPORT}")


def main():
    xls = pd.ExcelFile(FILE)
    # loads each sheet into a dict keyed by sheet name
    data = {s: load(xls, s) for s in SHEETS}
    for sheet, df in data.items():
        sheet_checks(df, sheet)

    c, d = data["Claims"], data["Disputes"]
    # reconcile reported totals against their component categories for each dataset.
    reconcile(c, "Claims", "claims", "number of claims", "total claims received",
              ["finalised claims", "withdrawn claims", "undetermined claims"],
              "Received = Finalised + Withdrawn + Undetermined")
    reconcile(c, "Claims", "claims", "number of claims", "finalised claims",
              ["finalised claims - admitted", "finalised claims - declined"], "Finalised = Admitted + Declined")
    reconcile(d, "Disputes", "disputes", "number of disputes", "disputes lodged",
              ["disputes resolved", "disputes withdrawn", "disputes undetermined"],
              "Lodged = Resolved + Withdrawn + Undetermined")
    reconcile(d, "Disputes", "disputes", "number of disputes", "disputes resolved",
              ["original decision maintained", "original decision reversed", "other dispute outcomes"],
              "Resolved = Maintained + Reversed + Other")
    industry_totals(data["Policy Statistics"])
    reason_sums(data["Other"])
    write_report()


if __name__ == "__main__":
    main()