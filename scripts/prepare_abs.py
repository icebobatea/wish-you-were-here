"""Prepare birthplace data for Victoria from the ABS historical population statistics.

Input:  3105065001ds0008_2014.xls  (ABS 3105.0.65.001 Australian Historical Population
        Statistics, 2014, Country of Birth data cube; download from abs.gov.au)
Output: data/vic_birthplace_1911.csv  Victorians born overseas in 1911, by country
                                      (named as on the Natural Earth map)
        data/vic_birthplace_trend.csv Victorians born in selected countries, every census

Run from the repo root:  python scripts/prepare_abs.py path/to/3105065001ds0008_2014.xls
"""
import re
import sys
import pandas as pd

# 1911 census birthplace names -> country name used on the Natural Earth map
MAP_1911 = {
    "England": "United Kingdom", "Scotland": "United Kingdom", "Wales": "United Kingdom",
    "Isle of Man": "United Kingdom", "Channel Islands": "United Kingdom",
    "British India": "India", "Goa": "India", "Ceylon": "Sri Lanka", "Burmah": "Myanmar",
    "Argentine Republic": "Argentina", "Rumania": "Romania", "Servia": "Serbia",
    "Siam": "Thailand", "Persia": "Iran", "Abyssinia": "Ethiopia", "Columbia": "Colombia",
    "Cape of Good Hope": "South Africa", "Natal": "South Africa", "Transvaal": "South Africa",
    "Orange Free State": "South Africa", "South Africa (undefined)": "South Africa",
    "Papua": "Papua New Guinea", "Philippine Is.": "Philippines",
    "Federated Malay States": "Malaysia", "Straits Settlements": "Malaysia",
    "New Hebrides": "Vanuatu", "Austria-Hungary": "Austria",
}
AUSTRALIAN = {"Commonwealth of Australia", "Victoria", "New South Wales", "Queensland",
              "South Australia", "Western Australia", "Tasmania", "Northern Territory",
              "Australia - undefined", "Federal Capital Territory"}

# Groups for the trend chart; each census names some countries slightly differently
TREND = {
    "Britain": ["England", "Scotland", "Wales", "England (incl. UK undefined)",
                "England (incl. United Kingdom undefined)"],
    "Ireland": ["Ireland", "Ireland (undefined)", "Ireland(d)", "Ireland, Republic of",
                "Ireland (Republic) incl. Ireland undefined", "Northern Ireland",
                "Republic of Ireland (incl. Ireland undefined)"],
    "Italy": ["Italy"],
    "Greece": ["Greece"],
    "India": ["India", "British India", "British India and Ceylon"],
    "China": ["China", "China (excl Taiwan Province)", "China (excluding Taiwan Province)",
              "China (excl. SARs and Taiwan Province)", "China (excl. SARs and Taiwan Province)(g)",
              "China (excl. SARs and Taiwan)"],
}


def read_victoria(path):
    """Victoria 'Persons' column from every national census table (8.7 to 8.23)."""
    x = pd.ExcelFile(path)
    rows = []
    for sheet in [f"Table 8.{i}" for i in range(7, 24)]:
        d = pd.read_excel(x, sheet, header=None)
        year = int(re.search(r"(19|20)\d\d", str(d.iloc[3, 0])).group(0))
        header = next(i for i in range(10) if (d.iloc[i] == "Victoria").any())
        vic_col = int((d.iloc[header] == "Victoria").to_numpy().nonzero()[0][0])
        persons = next(c for c in range(vic_col, vic_col + 4)
                       if str(d.iloc[header + 1, c]).strip().lower() == "persons")
        for i in range(header + 2, len(d)):
            name, value = d.iloc[i, 0], d.iloc[i, persons]
            if isinstance(name, str) and isinstance(value, (int, float)) and pd.notna(value):
                rows.append({"year": year, "birthplace": name.strip(), "persons": int(value)})
    return pd.DataFrame(rows)


def main(path):
    vic = read_victoria(path)

    y1911 = vic[(vic["year"] == 1911) & ~vic["birthplace"].isin(AUSTRALIAN)
                & ~vic["birthplace"].str.startswith("Total")
                & ~vic["birthplace"].str.contains("undefined|so described", regex=True)]
    y1911 = y1911.assign(country=y1911["birthplace"].replace(MAP_1911))
    choro = y1911.groupby("country", as_index=False)["persons"].sum()
    choro.sort_values("persons", ascending=False).to_csv("data/vic_birthplace_1911.csv", index=False)

    lookup = {name: group for group, names in TREND.items() for name in names}
    trend = vic[vic["birthplace"].isin(lookup)].assign(group=lambda d: d["birthplace"].map(lookup))
    trend = trend.groupby(["year", "group"], as_index=False)["persons"].sum()
    trend.to_csv("data/vic_birthplace_trend.csv", index=False)

    total_1911 = vic[(vic["year"] == 1911) & vic["birthplace"].str.startswith("Total")]["persons"].iat[0]
    print(f"1911: {choro['persons'].sum():,} of {total_1911:,} Victorians born overseas "
          f"({choro['persons'].sum() / total_1911:.0%})")


if __name__ == "__main__":
    main(sys.argv[1])
