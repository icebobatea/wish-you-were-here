"""Prepare chart-ready data from the Museums Victoria postcard export.

Input:  data/mv_postcards_raw.csv  (one row per item-association, exported from
        the Museums Victoria Collections API, query "postcard", item records)
Output: data/postcards.csv          (one row per postcard)
        data/depicted_countries.csv (postcards per depicted country, with centroid)

Run from the repo root:  python scripts/prepare.py
"""
import re
import pandas as pd

RAW = "data/mv_postcards_raw.csv"

# Museum place names -> modern country name used on the map
COUNTRY_FIX = {
    "England, Great Britain": "United Kingdom",
    "Great Britain": "United Kingdom",
    "England": "United Kingdom",
    "Scotland": "United Kingdom",
    "Scotland, Great Britain": "United Kingdom",
    "Mesopotamia (Iraq & Neighbours)": "Iraq",
    "Colony of Aden": "Yemen",
    "French Algeria": "Algeria",
    "Ceylon (Sri Lanka)": "Sri Lanka",
    "Gibraltar": "United Kingdom",
}
# Regions too vague to place on a map
DROP = {"Middle East", "Europe", "Islamic Empire", "British Overseas Territory"}

# Approximate country centroids (longitude, latitude) for symbol placement
CENTROIDS = {
    "Australia": (134.5, -25.7), "Egypt": (30.8, 26.8), "Iraq": (43.7, 33.2),
    "India": (78.9, 22.0), "United Kingdom": (-2.5, 54.0), "France": (2.4, 46.6),
    "Greece": (22.0, 39.3), "Yemen": (47.6, 15.6), "Algeria": (2.6, 28.0),
    "Argentina": (-64.0, -34.0), "South Africa": (24.7, -29.0), "Belgium": (4.6, 50.6),
    "Turkey": (35.2, 39.0), "Indonesia": (117.0, -2.5), "Cape Verde": (-23.6, 15.1),
    "Sri Lanka": (80.7, 7.9), "Japan": (138.3, 36.2), "Lebanon": (35.9, 33.9),
    "Romania": (25.0, 45.9), "Norway": (8.5, 61.0), "Germany": (10.4, 51.2),
    "Nepal": (84.1, 28.4),
}


def year_of(s):
    m = re.search(r"(1[89]\d\d|20\d\d)", str(s))
    return int(m.group(1)) if m else None


def theme_of(classifications):
    c = str(classifications)
    for key, label in [
        ("Royal exhibition", "Exhibition Building"),
        ("Military", "War & service"),
        ("Migration", "Migration"),
        ("Postal", "Everyday correspondence"),
    ]:
        if key in c:
            return label
    return "Other"


def main():
    raw = pd.read_csv(RAW)
    raw["year"] = raw["date"].map(year_of)

    items = raw.groupby("id").agg(
        title=("title", "first"),
        year=("year", "min"),
        classifications=("classifications", "first"),
        collections=("collections", "first"),
    ).reset_index()
    items["theme"] = items["classifications"].map(theme_of)
    items["year"] = items["year"].astype("Int64")
    items["decade"] = (items["year"] // 10 * 10).astype("Int64")

    dep = raw[raw["assoc_type"].str.contains("Depicted", na=False)].copy()
    dep["country"] = dep["country"].replace(COUNTRY_FIX)
    dep = dep[dep["country"].notna() & ~dep["country"].isin(DROP)]
    first_country = dep.drop_duplicates("id").set_index("id")["country"]
    items["depicted_country"] = items["id"].map(first_country)

    items.drop(columns=["classifications"]).to_csv("data/postcards.csv", index=False)

    counts = (dep.drop_duplicates(["id", "country"])
                 .merge(items[["id", "theme"]], on="id")
                 .groupby("country")
                 .agg(postcards=("id", "nunique"),
                      top_theme=("theme", lambda s: s.mode().iat[0]))
                 .reset_index())
    counts["longitude"] = counts["country"].map(lambda c: CENTROIDS[c][0])
    counts["latitude"] = counts["country"].map(lambda c: CENTROIDS[c][1])
    counts.sort_values("postcards", ascending=False).to_csv(
        "data/depicted_countries.csv", index=False)

    print(f"{len(items)} postcards, {items['year'].notna().sum()} dated, "
          f"{items['depicted_country'].notna().sum()} with a mappable depicted country")


if __name__ == "__main__":
    main()
