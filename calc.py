"""All the maths: targets, nutrition, daily summary, rolling averages, trend.

No Streamlit and no matplotlib in here, only pandas and numpy, so every
function can be tested on its own.
"""

import numpy as np
import pandas as pd

NUTRIENTS = ["Calories", "Proteins", "Carbs", "Fat", "Fibre"]

ACTIVITY_FACTORS = {
    "Sedentary": 1.2,
    "Lightly active": 1.375,
    "Moderately active": 1.55,
    "Very active": 1.725,
}

# Daily calorie adjustment applied to maintenance for each goal.
GOAL_ADJUSTMENT = {
    "Lose weight": -500,
    "Maintain weight": 0,
    "Gain weight": 300,
}

MIN_TARGET_KCAL = 1200   # safety floor for the calorie target
ON_TARGET_BAND = 0.10    # a day counts as "within budget" if intake is within +/-10%


# ------------------------------------------------------------------- targets

def bmr(gender, weight_kg, height_cm, age):
    """Basal metabolic rate (Mifflin-St Jeor). weight_kg may be a numpy array."""
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    return base + (5 if gender == "Male" else -161)


def daily_target(profile, weight_kg):
    """Calories per day for the user's goal. weight_kg may be a numpy array."""
    maintenance = bmr(
        profile["gender"], weight_kg, profile["height_cm"], profile["age"]
    ) * ACTIVITY_FACTORS[profile["activity"]]
    return np.maximum(np.floor(maintenance + GOAL_ADJUSTMENT[profile["goal"]]), MIN_TARGET_KCAL)


def macro_targets(target_kcal, weight_kg):
    """Grams per day: protein 1.6 g/kg, fat 25% of calories, carbs fill the rest."""
    protein = 1.6 * weight_kg
    fat = 0.25 * target_kcal / 9
    carbs = max((target_kcal - 4 * protein - 9 * fat) / 4, 50.0)
    fibre = 14 * target_kcal / 1000
    return {
        "Proteins": round(protein),
        "Carbs": round(carbs),
        "Fat": round(fat),
        "Fibre": round(fibre),
    }


# ----------------------------------------------------------------- nutrition

def nutrients_for(food_row, quantity):
    """Nutrients for a quantity of a food (pieces, or grams for 'g' foods)."""
    multiplier = quantity if food_row["Unit"] == "piece" else quantity / 100
    values = food_row[NUTRIENTS].to_numpy(dtype=float) * multiplier
    return dict(zip(NUTRIENTS, np.round(values, 2)))


def estimate_burn(met, weight_kg, minutes):
    """Calories burned = MET x body weight (kg) x hours."""
    return round(float(met) * weight_kg * minutes / 60)


# ----------------------------------------------------------- daily summary

SUMMARY_COLUMNS = [
    "Intake", "Proteins", "Carbs", "Fat", "Fibre", "Burned", "Weight",
    "Weight_used", "Target", "Budget", "Net", "Intake_7d", "Weight_7d", "Status",
]


def daily_summary(food, workouts, weights, profile, anchor):
    """One row per calendar day, built from the three logs.

    Days with no food logged have Intake = NaN (not 0), so a forgotten day
    never drags the averages down. Weight is interpolated between weigh-ins
    so each day's calorie target uses a sensible body weight.
    """
    anchor = pd.Timestamp(anchor).normalize()
    date_columns = [log["Date"] for log in (food, workouts, weights) if not log.empty]
    if not date_columns:
        return pd.DataFrame(columns=SUMMARY_COLUMNS, index=pd.DatetimeIndex([], name="Date"))

    start = min(d.min() for d in date_columns)
    end = max([anchor] + [d.max() for d in date_columns])
    days = pd.date_range(start, end, freq="D", name="Date")

    df = food.groupby("Date")[NUTRIENTS].sum().reindex(days)
    df = df.rename(columns={"Calories": "Intake"})
    df["Burned"] = workouts.groupby("Date")["Calories_Burned"].sum().reindex(days, fill_value=0.0)
    df["Weight"] = weights.groupby("Date")["Weight_kg"].mean().reindex(days)

    if df["Weight"].notna().any():
        df["Weight_used"] = df["Weight"].interpolate(limit_direction="both")
    else:
        df["Weight_used"] = float(profile["start_weight_kg"])

    df["Target"] = daily_target(profile, df["Weight_used"].to_numpy())
    df["Budget"] = df["Target"] + df["Burned"]
    df["Net"] = df["Intake"] - df["Burned"]

    # min_periods=1 -> average whatever is logged inside the 7-day window
    df["Intake_7d"] = df["Intake"].rolling(7, min_periods=1).mean()
    df["Weight_7d"] = df["Weight"].rolling(7, min_periods=1).mean()

    # Today is still in progress: being under budget early in the day is not "Under".
    ratio = df["Intake"] / df["Budget"]
    df["Status"] = np.select(
        [
            ratio.isna(),
            (df.index == anchor) & (ratio < 1 - ON_TARGET_BAND),
            ratio > 1 + ON_TARGET_BAND,
            ratio < 1 - ON_TARGET_BAND,
        ],
        ["No data", "In progress", "Over", "Under"],
        default="Within",
    )
    return df[SUMMARY_COLUMNS]


def window(df, anchor, days):
    """The last `days` days up to anchor (all rows if days is None)."""
    if days is None or df.empty:
        return df
    start = pd.Timestamp(anchor).normalize() - pd.to_timedelta(days - 1, unit="D")
    return df.loc[df.index >= start]


# ------------------------------------------------------------------- summaries

def kpis(df):
    """Headline numbers for a window of the daily summary."""
    logged = df["Intake"].dropna()
    weigh_ins = df["Weight"].dropna()
    return {
        "days_logged": int(logged.size),
        "avg_intake": float(logged.mean()) if logged.size else None,
        "avg_net": float(df["Net"].dropna().mean()) if logged.size else None,
        "avg_protein": float(df["Proteins"].dropna().mean()) if logged.size else None,
        "days_within": int((df["Status"] == "Within").sum()),
        "weight_change": float(weigh_ins.iloc[-1] - weigh_ins.iloc[0]) if weigh_ins.size >= 2 else None,
        "latest_weight": float(weigh_ins.iloc[-1]) if weigh_ins.size else None,
    }


def weight_trend(df, goal_weight):
    """Straight-line fit through the weigh-ins in df, plus a short message.

    Returns None when there is too little data for a trend to mean anything
    (fewer than 5 weigh-ins, or less than a week apart).
    """
    w = df["Weight"].dropna()
    if w.size < 5 or (w.index[-1] - w.index[0]).days < 6:
        return None

    x = (w.index - w.index[0]).days.to_numpy(dtype=float)
    slope, intercept = np.polyfit(x, w.to_numpy(), 1)   # kg per day, kg at day 0
    per_week = slope * 7
    now = intercept + slope * x[-1]
    gap = goal_weight - now

    if abs(gap) < 0.25:
        message = f"You are at your goal weight of {goal_weight:.1f} kg."
    elif abs(per_week) < 0.05:
        message = "Weight is holding steady, so there is no projected date for your goal."
    elif slope * gap < 0:
        message = f"Trend is {per_week:+.2f} kg/week, which is moving away from {goal_weight:.1f} kg."
    else:
        days_left = gap / slope
        if days_left > 730:
            message = f"Trend is {per_week:+.2f} kg/week, too slow to project a date for {goal_weight:.1f} kg."
        else:
            eta = w.index[-1] + pd.to_timedelta(days_left, unit="D")
            message = (
                f"Trend is {per_week:+.2f} kg/week. At this rate you reach "
                f"{goal_weight:.1f} kg around {eta:%d %b %Y}."
            )

    return {
        "x_start": w.index[0],
        "x_end": w.index[-1],
        "y_start": float(intercept),
        "y_end": float(now),
        "per_week": float(per_week),
        "message": message,
    }


def energy_split(df):
    """Share of calories from protein, carbs and fat (4/4/9 kcal per gram)."""
    grams = df[["Proteins", "Carbs", "Fat"]].sum().to_numpy(dtype=float)
    kcal = grams * np.array([4.0, 4.0, 9.0])
    total = kcal.sum()
    if total <= 0:
        return None
    return dict(zip(["Protein", "Carbs", "Fat"], kcal / total * 100))


def workout_totals(workouts):
    """Total calories burned and minutes per workout type, biggest first."""
    if workouts.empty:
        return pd.DataFrame(columns=["Calories_Burned", "Duration_min"])
    totals = workouts.groupby("Workout")[["Calories_Burned", "Duration_min"]].sum()
    return totals.sort_values("Calories_Burned", ascending=False)


def weekly_summary(df):
    """One row per week (weeks end on Sunday): the pandas resample showcase."""
    if df.empty:
        return pd.DataFrame()
    weekly = df.resample("W-SUN").agg(
        Days_logged=("Intake", "count"),
        Avg_intake=("Intake", "mean"),
        Avg_target=("Target", "mean"),
        Workout_kcal=("Burned", "sum"),
        Avg_weight=("Weight", "mean"),
    )
    weekly.index.name = "Week ending"
    return weekly.round(1)
