from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent
FILE = PROJECT_ROOT / "data/raw/Life insurance claims and disputes statistics database June 2018 to June 2026.xlsx"


def inspect_sheet_masking(xls: pd.ExcelFile, sheet: str) -> None:
    data = pd.read_excel(xls, sheet_name=sheet, dtype={"ABN": str})
    data.columns = [str(column).strip() for column in data.columns]

    required = {"ABN", "Company Name", "Value"}
    missing = required - set(data.columns)

    data["company_name"] = data["Company Name"].map(
        lambda value: value.strip() if isinstance(value, str) else value
    )
    data["abn"] = data["ABN"].map(
        lambda value: value.strip() if isinstance(value, str) else value
    )
    data["is_masked"] = data["Value"].map(
        lambda value: isinstance(value, str) and value.strip() == "*"
    )

    overall_masked = int(data["is_masked"].sum())
    overall_rows = len(data)
    overall_percent = 100 * overall_masked / overall_rows

    insurers = data[data["company_name"].str.lower().ne("total")].copy()
    insurer_summary = (
        insurers.groupby(["abn"], dropna=False)
        .agg(
            company_name=(
            "company_name",
            lambda names: " / ".join(sorted(names.dropna().unique()))), 
            rows=("is_masked", "size"), 
            masked=("is_masked", "sum")
        )
        .reset_index()
    )
    insurer_summary["visible"] = insurer_summary["rows"] - insurer_summary["masked"]
    insurer_summary["pct_masked"] = (
        100 * insurer_summary["masked"] / insurer_summary["rows"]
    )
    insurer_summary = insurer_summary.sort_values(
        ["pct_masked", "company_name"], ascending=[False, True]
    )

    print(
        f"{sheet} overall: {overall_masked:,} masked of {overall_rows:,} rows ({overall_percent:.1f}%)"
    )
    print(
        f"{sheet} insurer range: {insurer_summary['pct_masked'].min():.1f}% to "
        f"{insurer_summary['pct_masked'].max():.1f}% masked "
        f"({insurer_summary['abn'].nunique()} unique insurers)"
    )
    print(f"\n{sheet} masking by insurer (ABN groups renamed insurers together):")
    print(
        insurer_summary[
            ["company_name", "abn", "rows", "masked", "visible", "pct_masked"]
        ].to_string(
            index=False,
            formatters={"pct_masked": "{:.1f}%".format},
        )
    )


def inspect_masking(path: Path) -> None:
    xls = pd.ExcelFile(path)
    print(f"Source: {path.name}")
    for sheet in ["Claims", "Disputes"]:
        inspect_sheet_masking(xls, sheet)
        print()


if __name__ == "__main__":
    inspect_masking(FILE)
