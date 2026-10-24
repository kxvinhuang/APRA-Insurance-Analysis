from pathlib import Path
import pandas as pd

PREVIEW_ROWS = 10
PREVIEW_COLS = 12

file_path = Path("data/raw/Life insurance claims and disputes statistics database June 2018 to June 2026.xlsx")
RELEVANT_SHEETS = ['Policy Statistics', 'Claims', 'Disputes', 'Other']

def inspect(path: Path) -> None:
    xls = pd.ExcelFile(path)
    print(f"File: {path.name}")
    # show all worksheets and their names
    print(f"Sheets ({len(xls.sheet_names)}): {xls.sheet_names}")
    # show the relevant sheets and their names
    print(f"Relevant Sheets ({len(RELEVANT_SHEETS)}): {RELEVANT_SHEETS}\n")

    for name in RELEVANT_SHEETS:
        # doesnt use header=None as first row is col names
        raw = pd.read_excel(xls, sheet_name=name)
        # goes col by col and check each cell for "*", meaning its masked and gets the sum of all masked cells in the sheet
        masked = int((raw.astype(str).apply(lambda col: col.str.strip() == "*")).sum().sum())

        print("=" * 100)
        print(f"SHEET: {name!r}     raw dimensions (row, col): {raw.shape}     masked '*' cells: {masked}\n")
        # prints a preview of first 10 rows and 12 columns of the sheet, with max col width of 30 characters
        print(raw.iloc[:PREVIEW_ROWS, :PREVIEW_COLS].to_string(max_colwidth=30) + "\n")


if __name__ == "__main__":
    inspect(file_path)