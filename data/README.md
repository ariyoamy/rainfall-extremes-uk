# Data

This folder is filled by `rainfall_extremes.py` on first run. There is nothing
to download manually.

The script pulls daily precipitation totals from the Open-Meteo Historical
Weather API for each city listed in `CITIES`, saves the result as
`<city>.csv`, and re-uses those files on subsequent runs.

Source: https://open-meteo.com/en/docs/historical-weather-api  
Underlying dataset: ECMWF ERA5 reanalysis (~25 km resolution).
