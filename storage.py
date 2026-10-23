"""Reading and writing the CSV / JSON files.

Two kinds of files live in the data folder:

* Reference files (foods.csv, workouts.csv) are written once by hand and only read.
* Log files (food_log.csv, weight_log.csv, workout_log.csv) are filled by the
  user through the app, one row per event.

Every path is built from this file's own location, so the app works no matter
which folder you launch it from.
"""

import json
import os
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DEMO_DIR = BASE_DIR / "demo"

SCHEMAS = {
    "food_log": [
        "Date", "Meal", "Food", "Quantity", "Unit",
        "Calories", "Proteins", "Carbs", "Fat", "Fibre",
    ],
    "weight_log": ["Date", "Weight_kg"],
    "workout_log": ["Date", "Workout", "Duration_min", "Calories_Burned"],
}

NUMERIC_COLUMNS = {
    "food_log": ["Quantity", "Calories", "Proteins", "Carbs", "Fat", "Fibre"],
    "weight_log": ["Weight_kg"],
    "workout_log": ["Duration_min", "Calories_Burned"],
}

MEALS = ["Breakfast", "Lunch", "Snack", "Dinner"]

DEFAULT_PROFILE = {
    "gender": "Female",
    "age": 21,
    "height_cm": 166.0,
    "start_weight_kg": 52.0,
    "activity": "Lightly active",
    "goal": "Maintain weight",
    "goal_weight_kg": 52.0,
}


def data_dir(demo=False):
    """Folder holding the log files: demo/ for the sample data, data/ otherwise."""
    return DEMO_DIR if demo else DATA_DIR


# ---------------------------------------------------------------- reference files

def load_foods():
    """Nutrition table. Calories etc. are per 1 piece, or per 100 g."""
    return pd.read_csv(DATA_DIR / "foods.csv")


def load_workouts():
    """Workout types with their MET value (energy cost relative to resting)."""
    return pd.read_csv(DATA_DIR / "workouts.csv")


# -------------------------------------------------------------------- log files

def _read_raw(path, columns):
    """Read a log exactly as stored. The index is the row's position in the file."""
    try:
        df = pd.read_csv(path)
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return pd.DataFrame(columns=columns)
    for col in columns:
        if col not in df.columns:
            df[col] = pd.NA
    return df[columns]


def _write(path, df, columns):
    """Write through a temp file so a crash can never leave a half-written CSV."""
    out = df[columns].copy()
    # Dates we cannot read are left exactly as they were instead of crashing the save.
    parsed = pd.to_datetime(out["Date"], errors="coerce")
    out["Date"] = parsed.dt.strftime("%Y-%m-%d").fillna(out["Date"].astype(str))
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    out.to_csv(tmp, index=False)
    os.replace(tmp, path)


def load_log(name, folder):
    """Load a log with a real datetime Date column and numeric columns.

    The index keeps each row's position in the file, which is what
    delete_rows() uses to find the row again.
    """
    df = _read_raw(folder / f"{name}.csv", SCHEMAS[name])
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.normalize()
    for col in NUMERIC_COLUMNS[name]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if name == "food_log":
        df["Meal"] = df["Meal"].where(df["Meal"].isin(MEALS), "Snack")   # old files had no Meal
    return df.dropna(subset=["Date"])


def append_rows(name, folder, rows, replace_same_date=False):
    """Add rows (a list of dicts) to a log.

    With replace_same_date=True, existing rows on the same dates are removed
    first (used for weight: one weigh-in per day).
    """
    columns = SCHEMAS[name]
    path = folder / f"{name}.csv"
    raw = _read_raw(path, columns)
    new = pd.DataFrame(rows, columns=columns)

    if replace_same_date and not raw.empty:
        new_dates = set(pd.to_datetime(new["Date"]).dt.strftime("%Y-%m-%d"))
        old_dates = pd.to_datetime(raw["Date"], errors="coerce").dt.strftime("%Y-%m-%d")
        raw = raw[~old_dates.isin(new_dates)]

    combined = new if raw.empty else pd.concat([raw, new], ignore_index=True)
    _write(path, combined, columns)


def delete_rows(name, folder, labels):
    """Delete rows by the index labels that load_log() returned."""
    columns = SCHEMAS[name]
    path = folder / f"{name}.csv"
    raw = _read_raw(path, columns)
    _write(path, raw.drop(index=list(labels), errors="ignore"), columns)


def write_log(name, folder, df):
    """Replace a whole log (used by the demo-data generator)."""
    _write(folder / f"{name}.csv", df, SCHEMAS[name])


# ---------------------------------------------------------------------- profile

def load_profile(folder):
    """Profile saved in the folder, with defaults filling any missing key."""
    profile = dict(DEFAULT_PROFILE)
    try:
        with open(folder / "profile.json", encoding="utf-8") as f:
            profile.update(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return profile


def save_profile(folder, profile):
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / "profile.json.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)
    os.replace(tmp, folder / "profile.json")
