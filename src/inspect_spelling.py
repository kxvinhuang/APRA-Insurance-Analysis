from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
excel = PROJECT_ROOT / "data/raw/Life insurance claims and disputes statistics database June 2018 to June 2026.xlsx"
df = pd.read_excel(excel,
                   sheet_name="Disputes")
print(df["Data item"].value_counts())
print(df["Category"].value_counts())