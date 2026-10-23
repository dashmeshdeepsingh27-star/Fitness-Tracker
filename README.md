# Count before you Eat

A fitness tracker built with **pandas, numpy and matplotlib** (the app itself runs on Streamlit).
Log food, weight and workouts, then see progress curves, rolling averages and a weight trend.

## Run it

```
pip install -r requirements.txt
python -m streamlit run main.py
```

Open the browser tab it prints (usually http://localhost:8501).
Tick **Use demo data** in the sidebar to see 45 days of sample data without logging anything.

## Files

| File | What it is |
|---|---|
| `main.py` | The Streamlit app (three tabs: Today, Weight & workouts, Progress) |
| `calc.py` | Maths with pandas and numpy: targets, daily summary, rolling averages, trend line |
| `charts.py` | Every matplotlib chart, plus the four-panel dashboard |
| `storage.py` | Reads and writes the CSV and JSON files |
| `demo_data.py` | Makes the synthetic demo data with numpy random numbers |

## Data files

Reference files (written once, only read):

| File | Columns |
|---|---|
| `data/foods.csv` | Food, Unit (`piece` or `g`), Calories, Proteins, Carbs, Fat, Fibre. Values are per piece, or per 100 g. |
| `data/workouts.csv` | Workout, MET (how hard the activity is) |

Log files (filled in by you through the app, one row per entry):

| File | Columns |
|---|---|
| `data/food_log.csv` | Date, Meal, Food, Quantity, Unit, Calories, Proteins, Carbs, Fat, Fibre |
| `data/weight_log.csv` | Date, Weight_kg |
| `data/workout_log.csv` | Date, Workout, Duration_min, Calories_Burned |

`data/profile.json` stores your details. The `demo/` folder has the same three logs plus a profile,
filled with generated data.

To add a food, add a row to `data/foods.csv`. No code changes are needed.
Food values are typical approximations, not lab measurements.

## Where each library is used

* **pandas**: reading and writing the CSVs, `groupby` per day, `reindex` to fill missing days,
  `rolling(7)` averages, `interpolate`, `resample` for the weekly summary.
* **numpy**: `polyfit` for the weight trend line, `np.select` for over/under/within colouring,
  vectorised calorie targets, random numbers for the demo data.
* **matplotlib**: calories vs budget bars, weight with 7-day average and trend, workout bars,
  progress meters, calorie split, and a four-panel dashboard you can download as a PNG.
