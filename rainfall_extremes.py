"""
rainfall_extremes.py
--------------------
Daily precipitation extremes across UK cities, 1991-2024.

Pulls daily totals from Open-Meteo's historical archive (ERA5 reanalysis),
defines a separate "extreme" threshold for each city, and produces four
figures plus a summary CSV.

Run from the project root:
    python rainfall_extremes.py
"""

import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import cartopy.crs as ccrs
import cartopy.feature as cfeature


# ---------------------------------------------------------------
# Settings
# ---------------------------------------------------------------

YEAR_START = 1991
YEAR_END = 2024

# Spread of cities chosen for geographic variety (highlands, lowlands,
# coastal, inland), not just population. With only 12 points the goal
# is to cover the main rainfall regimes rather than every region.
CITIES = [
    ("London",     51.5074, -0.1278),
    ("Manchester", 53.4808, -2.2426),
    ("Birmingham", 52.4862, -1.8904),
    ("Cardiff",    51.4816, -3.1791),
    ("Edinburgh",  55.9533, -3.1883),
    ("Glasgow",    55.8642, -4.2518),
    ("Belfast",    54.5973, -5.9301),
    ("Plymouth",   50.3755, -4.1427),
    ("Newcastle",  54.9784, -1.6178),
    ("Aberdeen",   57.1497, -2.0943),
    ("Norwich",    52.6309,  1.2974),
    ("Inverness",  57.4778, -4.2247),
]

DATA_DIR = Path("data")
FIG_DIR = Path("figures")
OUT_DIR = Path("outputs")
for d in (DATA_DIR, FIG_DIR, OUT_DIR):
    d.mkdir(exist_ok=True)

# Below 1 mm is the standard climate-science cut-off for a "wet day".
# Including dry days in the percentile calculation drags the threshold
# down close to zero, which isn't what we want.
WET_DAY_MM = 1.0

# 95th percentile per city. Local rather than absolute, so a wet city
# (Inverness) and a drier one (Norwich) are each compared to themselves.
# This follows the ETCCDI R95p convention used in climate extremes work.
EXTREME_PERCENTILE = 95


# ---------------------------------------------------------------
# Download (with on-disk cache so re-runs are instant)
# ---------------------------------------------------------------

def fetch_city(name, lat, lon):
    cache = DATA_DIR / f"{name.lower()}.csv"
    if cache.exists():
        return pd.read_csv(cache, parse_dates=["date"])

    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": f"{YEAR_START}-01-01",
        "end_date": f"{YEAR_END}-12-31",
        "daily": "precipitation_sum",
        "timezone": "GMT",
    }
    r = requests.get(url, params=params, timeout=60)
    r.raise_for_status()
    j = r.json()

    out = pd.DataFrame({
        "date": pd.to_datetime(j["daily"]["time"]),
        "precip_mm": j["daily"]["precipitation_sum"],
    })
    out["city"] = name
    out.to_csv(cache, index=False)
    # Open-Meteo's free tier is generous but I'd rather not hammer it.
    time.sleep(2)
    return out


print("Loading city data...")
frames = []
for name, lat, lon in CITIES:
    print(f"  {name}")
    frames.append(fetch_city(name, lat, lon))

df = pd.concat(frames, ignore_index=True)
df["year"] = df["date"].dt.year
df["month"] = df["date"].dt.month

# Occasional NaN sneaks in at the edges of the archive. Drop them so
# the percentile isn't biased.
df = df.dropna(subset=["precip_mm"]).reset_index(drop=True)


# ---------------------------------------------------------------
# Per-city threshold and flag
# ---------------------------------------------------------------

thresholds = (
    df[df["precip_mm"] >= WET_DAY_MM]
      .groupby("city")["precip_mm"]
      .quantile(EXTREME_PERCENTILE / 100)
      .rename("threshold_mm")
)

df = df.merge(thresholds, on="city")
df["is_extreme"] = df["precip_mm"] >= df["threshold_mm"]


# ---------------------------------------------------------------
# Annual extreme-day counts (city x year)
# ---------------------------------------------------------------

annual = (
    df.groupby(["city", "year"])["is_extreme"]
      .sum()
      .reset_index(name="extreme_days")
)

# Sort cities by long-term average so the heatmap and trend plots
# read top-to-bottom from wettest to driest.
city_order = (
    annual.groupby("city")["extreme_days"]
          .mean()
          .sort_values(ascending=False)
          .index.tolist()
)


# ---------------------------------------------------------------
# Figure 1: UK map of mean annual extreme days
# ---------------------------------------------------------------

mean_extreme = annual.groupby("city")["extreme_days"].mean()

fig = plt.figure(figsize=(7.5, 8.5))
ax = plt.axes(projection=ccrs.Mercator())
ax.set_extent([-9, 2.5, 49.5, 60.5], crs=ccrs.PlateCarree())
ax.add_feature(cfeature.LAND, facecolor="#f4efe6")
ax.add_feature(cfeature.OCEAN, facecolor="#dbe7ef")
ax.add_feature(cfeature.COASTLINE, linewidth=0.5, edgecolor="#444")
ax.add_feature(cfeature.BORDERS, linewidth=0.4, linestyle=":", edgecolor="#666")

norm = mcolors.Normalize(vmin=mean_extreme.min(), vmax=mean_extreme.max())
cmap = plt.cm.viridis

for name, lat, lon in CITIES:
    val = mean_extreme[name]
    ax.scatter(lon, lat,
               s=200, color=cmap(norm(val)),
               edgecolor="black", linewidth=0.7,
               transform=ccrs.PlateCarree(), zorder=5)
    # Small offset so the label sits clear of the marker.
    ax.text(lon + 0.18, lat + 0.05, name,
            fontsize=8.5, weight="medium",
            transform=ccrs.PlateCarree(), zorder=6)

sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
sm.set_array([])
cbar = plt.colorbar(sm, ax=ax, fraction=0.035, pad=0.04, shrink=0.7)
cbar.set_label("Mean extreme days per year")

ax.set_title(f"Where extreme rainfall days happen most often\n"
             f"({YEAR_START}-{YEAR_END}, {EXTREME_PERCENTILE}th-percentile threshold per city)",
             fontsize=11, pad=12)
plt.savefig(FIG_DIR / "01_uk_map.png", dpi=200, bbox_inches="tight")
plt.close()


# ---------------------------------------------------------------
# Figure 2: heatmap of extreme days, city x year
# ---------------------------------------------------------------

heat = (
    annual.pivot(index="city", columns="year", values="extreme_days")
          .loc[city_order]
)

fig, ax = plt.subplots(figsize=(13, 5.5))
im = ax.imshow(heat.values, aspect="auto", cmap="YlGnBu")

ax.set_xticks(range(len(heat.columns)))
ax.set_xticklabels(heat.columns, rotation=45, ha="right", fontsize=8)
ax.set_yticks(range(len(heat.index)))
ax.set_yticklabels(heat.index, fontsize=9)
ax.set_xlabel("Year")
ax.set_title(f"Extreme rainfall days per year ({EXTREME_PERCENTILE}th-percentile, wet days only)",
             fontsize=11, pad=10)

cbar = plt.colorbar(im, ax=ax, pad=0.01)
cbar.set_label("Days per year")
plt.tight_layout()
plt.savefig(FIG_DIR / "02_extreme_days_heatmap.png", dpi=200)
plt.close()


# ---------------------------------------------------------------
# Figure 3: monthly seasonality
# ---------------------------------------------------------------

monthly = df.groupby(["city", "month"])["is_extreme"].sum().reset_index()
# Per-year so the y-axis is interpretable as "average extreme days
# in this month", regardless of how long the record is.
n_years = YEAR_END - YEAR_START + 1
monthly["per_year"] = monthly["is_extreme"] / n_years

fig, ax = plt.subplots(figsize=(10.5, 5.2))
month_labels = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]
colors = plt.cm.viridis(np.linspace(0, 0.95, len(city_order)))

for name, c in zip(city_order, colors):
    sub = monthly[monthly["city"] == name].sort_values("month")
    ax.plot(sub["month"], sub["per_year"],
            marker="o", linewidth=1.5, markersize=4.5,
            color=c, label=name)

ax.set_xticks(range(1, 13))
ax.set_xticklabels(month_labels)
ax.set_xlabel("Month")
ax.set_ylabel("Mean extreme days per month")
ax.set_title("When in the year do extremes happen?", fontsize=11, pad=10)
ax.grid(axis="y", linestyle=":", alpha=0.5)
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.13),
          ncol=6, fontsize=8, frameon=False)
plt.tight_layout()
plt.savefig(FIG_DIR / "03_monthly_seasonality.png", dpi=200, bbox_inches="tight")
plt.close()


# ---------------------------------------------------------------
# Figure 4: trends per city
# ---------------------------------------------------------------

fig, ax = plt.subplots(figsize=(11, 5.5))

for name, c in zip(city_order, colors):
    sub = annual[annual["city"] == name].sort_values("year").reset_index(drop=True)
    ax.plot(sub["year"], sub["extreme_days"],
            color=c, alpha=0.25, linewidth=1)

    # Linear trend. Not a hypothesis test - just shows the direction
    # and rough magnitude. The slope is in extra extreme days per year.
    coef = np.polyfit(sub["year"], sub["extreme_days"], 1)
    ax.plot(sub["year"], np.polyval(coef, sub["year"]),
            color=c, linewidth=2,
            label=f"{name} ({coef[0]:+.2f}/yr)")

ax.set_xlabel("Year")
ax.set_ylabel("Extreme days")
ax.set_title("Trend in annual extreme rainfall days", fontsize=11, pad=10)
ax.grid(axis="y", linestyle=":", alpha=0.5)
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.13),
          ncol=4, fontsize=7.5, frameon=False)
plt.tight_layout()
plt.savefig(FIG_DIR / "04_trends.png", dpi=200, bbox_inches="tight")
plt.close()


# ---------------------------------------------------------------
# Summary table
# ---------------------------------------------------------------

rows = []
for name in city_order:
    sub = df[df["city"] == name]
    wettest = sub.loc[sub["precip_mm"].idxmax()]
    ann = annual[annual["city"] == name]
    wettest_year_row = ann.loc[ann["extreme_days"].idxmax()]

    rows.append({
        "city": name,
        "threshold_mm": round(thresholds[name], 1),
        "max_daily_mm": round(sub["precip_mm"].max(), 1),
        "max_daily_date": wettest["date"].strftime("%Y-%m-%d"),
        "mean_extreme_days_per_year": round(ann["extreme_days"].mean(), 1),
        "wettest_year": int(wettest_year_row["year"]),
        "extreme_days_in_wettest_year": int(wettest_year_row["extreme_days"]),
    })

summary = pd.DataFrame(rows)
summary.to_csv(OUT_DIR / "summary.csv", index=False)

print()
print("Per-city summary")
print("-" * 80)
print(summary.to_string(index=False))
print()
print(f"Figures saved to {FIG_DIR}/")
print(f"Summary saved to {OUT_DIR}/summary.csv")
