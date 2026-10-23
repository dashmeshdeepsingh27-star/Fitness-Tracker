"""Generate realistic synthetic data for the demo (and for the presentation).

Nothing here is real: it is made with numpy random numbers so the charts have
45 days of history to show. Run `python demo_data.py` to regenerate it, or use
the button in the app (it also moves the dates so the data ends today).
"""

import numpy as np
import pandas as pd

import calc
import storage

DEMO_PROFILE = {
    "gender": "Male",
    "age": 21,
    "height_cm": 175.0,
    "start_weight_kg": 74.0,
    "activity": "Lightly active",
    "goal": "Lose weight",
    "goal_weight_kg": 70.0,
}

# One workout per weekday (Monday = 0): (name, base minutes). Sunday is rest.
WEEK_PLAN = {
    0: ("Weight training", 60),
    1: ("Running", 30),
    2: ("Weight training", 60),
    3: ("Badminton", 45),
    4: ("Weight training", 60),
    5: ("Football", 60),
}


def _grams(rng, low, high):
    """A random gram quantity in steps of 10."""
    return int(rng.integers(low // 10, high // 10 + 1) * 10)


def _breakfast(rng):
    pick = rng.integers(4)
    if pick == 0:
        return [("Oats", _grams(rng, 50, 70)), ("Milk", _grams(rng, 200, 250)), ("Banana", 1)]
    if pick == 1:
        return [("Egg", int(rng.integers(2, 4))), ("Bread slice", 2)]
    if pick == 2:
        return [("Idli", int(rng.integers(3, 5))), ("Dal", _grams(rng, 100, 150))]
    return [("Paratha", 1), ("Curd", _grams(rng, 100, 150))]


def _lunch(rng):
    items = [
        ("Roti", int(rng.integers(2, 4))),
        ("Dal", _grams(rng, 120, 200)),
        ("Mixed veg curry", _grams(rng, 100, 150)),
        (str(rng.choice(["Paneer", "Chicken", "Rajma (cooked)", "Chole (cooked)"])), _grams(rng, 80, 120)),
    ]
    if rng.random() < 0.4:
        items.append(("Rice (cooked)", _grams(rng, 100, 150)))
    return items


def _snack(rng):
    options = [
        [("Peanuts", _grams(rng, 20, 30))],
        [("Banana", 1)],
        [("Apple", 1)],
        [("Whey protein scoop", 1), ("Milk", _grams(rng, 200, 250))],
        [("Almonds", _grams(rng, 20, 30))],
        [("Curd", _grams(rng, 100, 150))],
    ]
    return options[int(rng.integers(len(options)))]


def _dinner(rng):
    protein = [
        ("Chicken", _grams(rng, 100, 150)),
        ("Paneer", _grams(rng, 80, 120)),
        ("Soya chunks (dry)", _grams(rng, 30, 40)),
        ("Rajma (cooked)", _grams(rng, 150, 200)),
    ][int(rng.integers(4))]
    items = [("Roti", int(rng.integers(2, 4))), protein, ("Mixed veg curry", _grams(rng, 100, 150))]
    if rng.random() < 0.5:
        items.append(("Dal", _grams(rng, 100, 150)))
    return items


def _scale_grams(items, foods, goal_kcal):
    """Scale the gram-based items so the whole day lands near goal_kcal.

    Pieces (eggs, rotis...) stay as they are; only grams are scaled.
    """
    def kcal(food, qty):
        return calc.nutrients_for(foods.loc[food], qty)["Calories"]

    fixed = sum(kcal(f, q) for _, f, q in items if foods.loc[f, "Unit"] == "piece")
    flexible = sum(kcal(f, q) for _, f, q in items if foods.loc[f, "Unit"] == "g")
    factor = float(np.clip((goal_kcal - fixed) / flexible, 0.5, 1.8)) if flexible > 0 else 1.0

    scaled = []
    for meal, food, qty in items:
        if foods.loc[food, "Unit"] == "g":
            qty = max(10, int(round(qty * factor / 10)) * 10)
        scaled.append((meal, food, qty))
    return scaled


def generate(folder, days=45, seed=42, end_date=None):
    """Write food_log, weight_log, workout_log and profile.json into folder."""
    rng = np.random.default_rng(seed)
    foods = storage.load_foods().set_index("Food", drop=False)
    mets = storage.load_workouts().set_index("Workout")["MET"]

    end = pd.Timestamp(end_date if end_date is not None else pd.Timestamp.today()).normalize()
    dates = pd.date_range(end=end, periods=days)
    forgot = set(rng.choice(np.arange(5, days - 1), size=3, replace=False).tolist())

    # The true body weight drifts down about 0.5 kg a week.
    true_weight = 74.0 - 0.07 * np.arange(days)

    food_rows, weight_rows, workout_rows = [], [], []
    for i, date in enumerate(dates):
        weight = float(true_weight[i])

        # --- workout (15% of planned sessions are skipped)
        burn = 0
        plan = WEEK_PLAN.get(date.weekday())
        if plan and rng.random() > 0.15:
            name, base = plan
            minutes = int(base + 5 * rng.integers(-2, 3))
            burn = calc.estimate_burn(mets[name], weight, minutes)
            workout_rows.append({"Date": date, "Workout": name,
                                 "Duration_min": minutes, "Calories_Burned": burn})
        elif date.weekday() == 6 and rng.random() < 0.5:
            minutes = int(30 + 5 * rng.integers(0, 3))
            burn = calc.estimate_burn(mets["Walking (brisk)"], weight, minutes)
            workout_rows.append({"Date": date, "Workout": "Walking (brisk)",
                                 "Duration_min": minutes, "Calories_Burned": burn})

        # --- weigh-in on about 80% of days
        if rng.random() < 0.8:
            weight_rows.append({"Date": date, "Weight_kg": round(weight + rng.normal(0, 0.3), 1)})

        # --- food
        if i in forgot:
            continue
        if i == days - 1:
            # today: only breakfast and lunch so far
            items = [("Breakfast", f, q) for f, q in _breakfast(rng)]
            items += [("Lunch", f, q) for f, q in _lunch(rng)]
        else:
            items = [("Breakfast", f, q) for f, q in _breakfast(rng)]
            items += [("Lunch", f, q) for f, q in _lunch(rng)]
            items += [("Snack", f, q) for f, q in _snack(rng)]
            items += [("Dinner", f, q) for f, q in _dinner(rng)]

            budget = float(calc.daily_target(DEMO_PROFILE, weight)) + burn
            roll = rng.random()
            if roll < 0.18:                      # treat day
                items.append(("Snack", "Samosa", 2))
                ratio = rng.uniform(1.18, 1.35)
            elif roll < 0.36:                    # light day
                ratio = rng.uniform(0.72, 0.85)
            else:                                # normal day
                ratio = rng.normal(0.99, 0.07)
            items = _scale_grams(items, foods, budget * ratio)

        for meal, food, qty in items:
            row = foods.loc[food]
            food_rows.append({
                "Date": date, "Meal": meal, "Food": food,
                "Quantity": qty, "Unit": row["Unit"],
                **calc.nutrients_for(row, qty),
            })

    folder.mkdir(parents=True, exist_ok=True)
    storage.write_log("food_log", folder, pd.DataFrame(food_rows))
    storage.write_log("weight_log", folder, pd.DataFrame(weight_rows))
    storage.write_log("workout_log", folder, pd.DataFrame(workout_rows))
    storage.save_profile(folder, DEMO_PROFILE)


if __name__ == "__main__":
    generate(storage.DEMO_DIR)
    print(f"Demo data written to {storage.DEMO_DIR}")
