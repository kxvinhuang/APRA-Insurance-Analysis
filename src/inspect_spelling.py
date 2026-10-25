import pandas as pd

df = pd.read_excel("data/raw/Life insurance claims and disputes statistics database June 2018 to June 2026.xlsx",
                   sheet_name="Disputes")
print(df["Data item"].value_counts())
print(df["Category"].value_counts())