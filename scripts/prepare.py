"""Prepare chart-ready data from the Museums Victoria postcard export.

Input:  data/mv_postcards_raw.csv  (one row per item-association, exported from
        the Museums Victoria Collections API, query "postcard", item records)
Also:  data/ref/vic_suburb_coords.csv (Victorian suburb coordinates: the VIC rows of the
        Australian Postcodes dataset, github.com/matthewproctor/australianpostcodes,
        averaged per suburb name)
        data/victoria.geojson (Victoria outline, from the states.geojson file at
        github.com/rowanhogan/australian-states; used directly by the map)
Output: data/postcards.csv           one row per postcard
        data/depicted_countries.csv  postcards per depicted country, with centroid
        data/depicted_by_theme.csv   top depicted countries split by theme
        data/waffle.csv              100 squares split by theme share
        data/theme_shift.csv         theme share before vs after 1920
        data/theme_span.csv          year range of each theme
        data/collections.csv         postcards per museum collection
        data/flows.csv / flows.geojson  sender country -> recipient country
        data/flow_places.csv         places at either end of a flow
        data/vic_localities.csv      postcards linked to each Victorian place

Run from the repo root:  python scripts/prepare.py
"""
import json
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


# Representative points for sender/recipient places (approximate city coordinates)
FLOW_POINTS = {
    "Australia": ("Melbourne", 144.96, -37.81), "Scotland": ("Paisley", -4.42, 55.85),
    "England": ("London", -0.13, 51.51), "United States of America": ("USA", -98.0, 39.0),
    "South Africa": ("Cape Town", 18.42, -33.92), "Nigeria": ("Nigeria", 8.7, 9.1),
    "India": ("India", 78.9, 22.0), "Egypt": ("Cairo", 31.24, 30.04),
    "Greece": ("Athens", 23.73, 37.98), "France": ("Paris", 2.35, 48.86),
    "New Zealand": ("Wellington", 174.78, -41.29), "New Guinea": ("New Guinea", 145.0, -6.3),
    "Ottoman Empire": ("Ottoman Empire", 35.2, 39.0), "Singapore": ("Singapore", 103.82, 1.35),
}
FLOW_FIX = {"Scotland, Great Britain": "Scotland", "England, Great Britain": "England"}

THEMES = ["Exhibition Building", "War & service", "Migration",
          "Everyday correspondence", "Other"]


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

    # Top depicted countries split by theme (stacked bar)
    top = counts.sort_values("postcards", ascending=False)["country"].head(9)
    dbt = (items[items["depicted_country"].isin(top)]
           .groupby(["depicted_country", "theme"]).size().reset_index(name="postcards"))
    dbt.to_csv("data/depicted_by_theme.csv", index=False)

    # Waffle: 100 squares, shares rounded with largest remainder so they sum to 100
    share = items["theme"].value_counts().reindex(THEMES).fillna(0)
    exact = share / share.sum() * 100
    squares = exact.astype(int)
    for t in (exact - squares).sort_values(ascending=False).index[: 100 - squares.sum()]:
        squares[t] += 1
    cells = [t for t in THEMES for _ in range(squares[t])]
    pd.DataFrame({"theme": cells, "i": range(100)}).assign(
        col=lambda d: d["i"] % 10, row=lambda d: d["i"] // 10,
        share=lambda d: d["theme"].map(squares),
    ).to_csv("data/waffle.csv", index=False)

    # Dumbbell: share of each theme among dated cards before 1920 vs 1920 onwards
    # Postcards were first issued in 1869, so earlier years refer to the scene, not the card
    dated = items[items["year"] >= 1869].copy()
    dated["era"] = dated["year"].map(lambda y: "Before 1920" if y < 1920 else "1920 onwards")
    shift = (dated.groupby("era")["theme"].value_counts(normalize=True)
             .rename("share").reset_index())
    shift["share"] = (shift["share"] * 100).round(1)
    shift.to_csv("data/theme_shift.csv", index=False)

    # Range plot: first and last year of each theme, plus the middle half of its cards
    span = dated.groupby("theme")["year"].agg(
        first="min", last="max",
        mid_start=lambda y: int(y.quantile(0.25)), mid_end=lambda y: int(y.quantile(0.75)),
        cards="count").reset_index()
    span.to_csv("data/theme_span.csv", index=False)

    # Museum collections the cards belong to
    coll = (items["collections"].fillna("No named collection").str.split("; ")
            .explode().value_counts().reset_index())
    coll.columns = ["collection", "postcards"]
    coll["collection"] = coll["collection"].str.replace("Returned and Services League (RSL)", "RSL", regex=False)
    coll.head(8).to_csv("data/collections.csv", index=False)

    # Flows: sender country -> recipient country (international only)
    snd = raw[raw["assoc_type"].isin(["Sender", "Place & Date Written", "Place & Date Used"])]
    rcv = raw[raw["assoc_type"] == "Addressed To"]
    f = snd[["id", "country"]].merge(rcv[["id", "country"]], on="id", suffixes=("_from", "_to"))
    f = f.replace({"country_from": FLOW_FIX, "country_to": FLOW_FIX}).drop_duplicates()
    f = f[f["country_from"].isin(FLOW_POINTS) & f["country_to"].isin(FLOW_POINTS)
          & (f["country_from"] != f["country_to"])]
    flows = f.groupby(["country_from", "country_to"]).size().reset_index(name="postcards")
    for end in ("from", "to"):
        pts = flows[f"country_{end}"].map(FLOW_POINTS)
        flows[f"place_{end}"] = pts.str[0]
        flows[f"lon_{end}"] = pts.str[1]
        flows[f"lat_{end}"] = pts.str[2]
    flows.to_csv("data/flows.csv", index=False)
    # Places at either end of a flow, with cards sent and received (for map labels)
    ends = pd.concat([
        flows.rename(columns={"place_from": "place", "lon_from": "lon", "lat_from": "lat"})
             .assign(sent=flows["postcards"], received=0)[["place", "lon", "lat", "sent", "received"]],
        flows.rename(columns={"place_to": "place", "lon_to": "lon", "lat_to": "lat"})
             .assign(sent=0, received=flows["postcards"])[["place", "lon", "lat", "sent", "received"]],
    ]).groupby(["place", "lon", "lat"], as_index=False)[["sent", "received"]].sum()
    ends.to_csv("data/flow_places.csv", index=False)

    # Same flows as GeoJSON lines so the map draws them as great-circle routes
    feats = []
    for rec in flows.to_dict("records"):
        line = [[rec["lon_from"], rec["lat_from"]], [rec["lon_to"], rec["lat_to"]]]
        feats.append({"type": "Feature", "properties": rec,
                      "geometry": {"type": "LineString", "coordinates": line}})
    with open("data/flows.geojson", "w") as fh:
        json.dump({"type": "FeatureCollection", "features": feats}, fh, default=int)

    # Victorian places linked to each postcard (any association: depicted, sent, made...)
    coords = pd.read_csv("data/ref/vic_suburb_coords.csv")
    coords["key"] = coords["locality"].str.upper()
    vic = raw[raw["state"] == "Victoria"].dropna(subset=["locality"]).copy()
    vic["place"] = vic["locality"].str.replace(" District", "", regex=False).str.strip().str.title()
    vic["key"] = vic["place"].str.upper()
    vic = vic.drop_duplicates(["id", "key"]).merge(coords[["key", "lat", "lon"]], on="key")
    vic = vic.merge(items[["id", "theme"]], on="id")
    vl = (vic.groupby(["place", "lat", "lon"])
          .agg(postcards=("id", "nunique"), top_theme=("theme", lambda s: s.mode().iat[0]))
          .reset_index().sort_values("postcards", ascending=False))
    vl.to_csv("data/vic_localities.csv", index=False)

    print(f"{len(items)} postcards, {items['year'].notna().sum()} dated, "
          f"{items['depicted_country'].notna().sum()} with a mappable depicted country")


if __name__ == "__main__":
    main()
