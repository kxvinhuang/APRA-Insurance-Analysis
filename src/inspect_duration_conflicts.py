import pandas as pd
from pathlib import Path

excel = Path("data/raw/Life insurance claims and disputes statistics database June 2018 to June 2026.xlsx")
df = pd.read_excel(excel, sheet_name="Claims", dtype={"ABN": str})
csv = Path("docs/conflicting_duplicates_claims.csv")
conf = pd.read_csv(csv)
conf["reporting_date"] = pd.to_datetime(conf["reporting_date"])

for _, g in conf.groupby(["reporting_date", "company_name", "channel_type", "cover_type"]):
    # get first row of group to use as a reference for filtering the original dataframe
    r = g.iloc[0]
    block = df[(df["Reporting Date"] == r.reporting_date)
               & (df["Company Name"].str.strip() == r.company_name)
               & (df["Channel Type"].str.strip() == r.channel_type)
               & (df["Cover Type"].str.strip() == r.cover_type)
               & (df["Subject"].str.strip() == "Claims Duration")]
    print(f"\n{r.company_name} | {r.cover_type} | {r.channel_type} | {r.reporting_date.date()}")
    # add excel row column to show original row number in excel file, which is index + 2 since excel has a header row and pandas uses 0-based indexing
    print(block.assign(excel_row=block.index + 2)[["excel_row", "Data item", "Value"]].to_string(index=False))