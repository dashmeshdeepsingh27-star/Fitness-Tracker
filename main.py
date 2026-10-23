"""Count before you Eat: a fitness tracker for food, weight and workouts.

Run with:  python -m streamlit run main.py
"""

import pandas as pd
import streamlit as st

import calc
import charts
import demo_data
import storage

st.set_page_config(page_title="Count before you Eat", layout="wide")
st.title("Count before you Eat")
st.caption("Log your food, weight and workouts, then watch your progress.")

# `version` changes after every write, which gives each table a fresh editor state.
if "version" not in st.session_state:
    st.session_state.version = 0
if "flash" in st.session_state:
    st.toast(st.session_state.pop("flash"))


def done(message):
    """Show a message, then rerun the page so it reads the updated files."""
    st.session_state.version += 1
    st.session_state.flash = message
    st.rerun()


# ------------------------------------------------------------------ sidebar

with st.sidebar:
    demo = st.toggle(
        "Use demo data",
        help="45 days of made-up data so the charts have something to show. "
             "Your real logs are not touched.",
    )
    mode = "demo" if demo else "real"
    folder = storage.data_dir(demo)

    if demo and not (folder / "food_log.csv").exists():
        demo_data.generate(folder)
    if demo and st.button("Regenerate demo data", help="Rebuilds the sample so it ends today."):
        demo_data.generate(folder)
        done("Demo data regenerated")

    st.header("Your details")
    saved = storage.load_profile(folder)
    genders = ["Female", "Male"]
    activities = list(calc.ACTIVITY_FACTORS)
    goals = list(calc.GOAL_ADJUSTMENT)

    gender = st.radio("Gender", genders, index=genders.index(saved["gender"]),
                      horizontal=True, key=f"gender_{mode}")
    age = st.number_input("Age (years)", min_value=10, max_value=100,
                          value=int(saved["age"]), step=1, key=f"age_{mode}")
    height = st.number_input("Height (cm)", min_value=100.0, max_value=230.0,
                             value=float(saved["height_cm"]), step=0.5, key=f"height_{mode}")
    start_weight = st.number_input(
        "Starting weight (kg)", min_value=30.0, max_value=250.0,
        value=float(saved["start_weight_kg"]), step=0.5, key=f"start_weight_{mode}",
        help="Used until you log your first weigh-in.")
    activity = st.selectbox(
        "Usual daily activity", activities, index=activities.index(saved["activity"]),
        key=f"activity_{mode}",
        help="Your normal day outside the workouts you log. Logged workouts are added on top.")
    goal = st.selectbox("Goal", goals, index=goals.index(saved["goal"]), key=f"goal_{mode}")
    goal_weight = st.number_input("Goal weight (kg)", min_value=30.0, max_value=250.0,
                                  value=float(saved["goal_weight_kg"]), step=0.5,
                                  key=f"goal_weight_{mode}")

    profile = {
        "gender": gender, "age": int(age), "height_cm": float(height),
        "start_weight_kg": float(start_weight), "activity": activity,
        "goal": goal, "goal_weight_kg": float(goal_weight),
    }
    if profile != saved:
        storage.save_profile(folder, profile)

    with st.expander("How the numbers work"):
        st.markdown(
            "- **Target** = BMR (Mifflin-St Jeor) x activity factor, then "
            "-500 / 0 / +300 kcal for your goal (never below 1,200).\n"
            "- **Budget** = target + calories burned in the workouts you logged.\n"
            "- **Burn** = MET x body weight (kg) x hours.\n"
            "- **Protein** 1.6 g per kg, **fat** 25% of calories, **fibre** 14 g per "
            "1,000 kcal, **carbs** fill the rest.\n"
            "- A day counts as **within budget** if you ate within 10% of it.\n"
            "- Days with no food logged are skipped, not counted as zero."
        )

# --------------------------------------------------------------------- data

food = storage.load_log("food_log", folder)
weights = storage.load_log("weight_log", folder).sort_values("Date")
workouts = storage.load_log("workout_log", folder)
foods = storage.load_foods()
workout_types = storage.load_workouts()

today = pd.Timestamp.today().normalize()
latest_dates = [log["Date"].max() for log in (food, weights, workouts) if not log.empty]
# Demo data may be older than today; treat its last day as "today" so it still looks current.
anchor = max(latest_dates) if (demo and latest_dates) else today
latest_date_allowed = max(today, anchor).date()

latest_weight = float(weights["Weight_kg"].iloc[-1]) if not weights.empty else profile["start_weight_kg"]
daily = calc.daily_summary(food, workouts, weights, profile, anchor)


def day_snapshot(day):
    """What was eaten on a day, and the calorie budget and nutrient targets for it."""
    day = pd.Timestamp(day).normalize()
    eaten = food.loc[food["Date"] == day, calc.NUTRIENTS].sum()
    burned = float(workouts.loc[workouts["Date"] == day, "Calories_Burned"].sum())
    weight = float(daily["Weight_used"].get(day, latest_weight))
    target = int(calc.daily_target(profile, weight))
    targets = calc.macro_targets(target, weight)
    targets["Calories"] = target + burned
    return {
        "consumed": {name: float(eaten[name]) for name in calc.NUTRIENTS},
        "targets": targets,
        "target": target,
        "burned": burned,
    }


def deletable_table(log_name, rows, columns, config, key):
    """Show log rows with a Delete tick-box column and a button to remove the ticked ones."""
    if rows.empty:
        st.caption("Nothing logged yet.")
        return
    view = rows[columns].copy()
    view.insert(0, "Delete", False)
    edited = st.data_editor(
        view, hide_index=True, disabled=columns,
        column_config={"Delete": st.column_config.CheckboxColumn("Delete", width="small"), **config},
        key=f"{key}_{st.session_state.version}",
    )
    picked = list(edited.index[edited["Delete"]])
    if st.button("Delete selected", key=f"{key}_delete", disabled=not picked):
        storage.delete_rows(log_name, folder, picked)
        done(f"Deleted {len(picked)} {'entry' if len(picked) == 1 else 'entries'}")


@st.cache_data(show_spinner=False)
def dashboard_png(view, trend, goal_weight, totals, consumed, targets, heading):
    """The four-panel dashboard as PNG bytes (cached until its inputs change)."""
    fig = charts.fig_dashboard(view, trend, goal_weight, totals, consumed, targets, heading)
    return charts.figure_to_png(fig)


tab_today, tab_log, tab_progress = st.tabs(["Today", "Weight & workouts", "Progress"])

# ---------------------------------------------------------------- Today tab

with tab_today:
    day = st.date_input("Date", value=anchor.date(), max_value=latest_date_allowed,
                        key=f"day_{mode}")
    day_ts = pd.Timestamp(day)
    snap = day_snapshot(day_ts)

    add_col, summary_col = st.columns([1, 1.2], gap="large")

    with add_col:
        with st.container(border=True):
            st.subheader("Add food")
            meal = st.selectbox("Meal", storage.MEALS, key="meal")
            choice = st.selectbox("Food", foods["Food"], index=None,
                                  placeholder="Choose a food", key="food_choice")

            if choice is None:
                st.number_input("Quantity", value=1, disabled=True, key="qty_none")
                st.button("Add to log", type="primary", disabled=True)
            else:
                row = foods[foods["Food"] == choice].iloc[0]
                if row["Unit"] == "piece":
                    quantity = st.number_input("Quantity (pieces)", min_value=1, max_value=50,
                                               value=1, step=1, key=f"qty_{choice}")
                else:
                    quantity = st.number_input("Quantity (grams)", min_value=5, max_value=2000,
                                               value=100, step=5, key=f"qty_{choice}")

                nutrients = calc.nutrients_for(row, quantity)
                st.metric("This portion", f"{nutrients['Calories']:.0f} kcal")
                st.caption(
                    f"Protein {nutrients['Proteins']:.1f} g  ·  Carbs {nutrients['Carbs']:.1f} g  ·  "
                    f"Fat {nutrients['Fat']:.1f} g  ·  Fibre {nutrients['Fibre']:.1f} g"
                )

                if st.button("Add to log", type="primary"):
                    storage.append_rows("food_log", folder, [{
                        "Date": day_ts, "Meal": meal, "Food": choice,
                        "Quantity": quantity, "Unit": row["Unit"], **nutrients,
                    }])
                    done(f"Added {choice} to {meal.lower()} on {day_ts:%d %b}")

    with summary_col:
        eaten = snap["consumed"]["Calories"]
        budget = snap["targets"]["Calories"]
        left = budget - eaten

        eaten_col, budget_col, left_col = st.columns(3)
        eaten_col.metric("Eaten", f"{eaten:,.0f} kcal")
        budget_col.metric(
            "Budget", f"{budget:,.0f} kcal",
            help=f"Daily target {snap['target']:,} kcal + {snap['burned']:,.0f} kcal burned in workouts.")
        left_col.metric("Left" if left >= 0 else "Over by", f"{abs(left):,.0f} kcal")
        st.progress(min(eaten / budget, 1.0) if budget else 0.0)
        st.pyplot(charts.fig_macros(snap["consumed"], snap["targets"]))

    st.subheader(f"Food logged on {day_ts:%d %b %Y}")
    entries = food[food["Date"] == day_ts]
    entries = entries.sort_values("Meal", key=lambda meals: meals.map(storage.MEALS.index),
                                  kind="stable")
    deletable_table(
        "food_log", entries,
        ["Meal", "Food", "Quantity", "Unit", "Calories", "Proteins", "Carbs", "Fat", "Fibre"],
        {"Calories": st.column_config.NumberColumn(format="%.0f"),
         "Proteins": st.column_config.NumberColumn(format="%.1f"),
         "Carbs": st.column_config.NumberColumn(format="%.1f"),
         "Fat": st.column_config.NumberColumn(format="%.1f"),
         "Fibre": st.column_config.NumberColumn(format="%.1f")},
        key="food_table",
    )

# -------------------------------------------------------- Weight & workouts

with tab_log:
    weight_col, workout_col = st.columns(2, gap="large")

    with weight_col:
        with st.container(border=True):
            st.subheader("Weigh-in")
            weigh_day = st.date_input("Date", value=anchor.date(), max_value=latest_date_allowed,
                                      key=f"weigh_day_{mode}")
            weigh_value = st.number_input("Weight (kg)", min_value=20.0, max_value=300.0,
                                          value=round(latest_weight, 1), step=0.1, format="%.1f",
                                          key=f"weigh_value_{mode}")
            if st.button("Save weigh-in", type="primary"):
                storage.append_rows(
                    "weight_log", folder,
                    [{"Date": pd.Timestamp(weigh_day), "Weight_kg": round(weigh_value, 1)}],
                    replace_same_date=True)
                done(f"Saved {weigh_value:.1f} kg for {pd.Timestamp(weigh_day):%d %b}")

        st.subheader("Recent weigh-ins")
        deletable_table(
            "weight_log", weights.sort_values("Date", ascending=False).head(10),
            ["Date", "Weight_kg"],
            {"Date": st.column_config.DateColumn(format="DD MMM YYYY"),
             "Weight_kg": st.column_config.NumberColumn("Weight (kg)", format="%.1f")},
            key="weight_table",
        )

    with workout_col:
        with st.container(border=True):
            st.subheader("Workout")
            workout_day = st.date_input("Date", value=anchor.date(), max_value=latest_date_allowed,
                                        key=f"workout_day_{mode}")
            kind = st.selectbox("Workout", workout_types["Workout"], key="workout_kind")
            minutes = st.number_input("Duration (minutes)", min_value=5, max_value=300,
                                      value=30, step=5, key="workout_minutes")
            met = float(workout_types.loc[workout_types["Workout"] == kind, "MET"].iloc[0])
            burn = calc.estimate_burn(met, latest_weight, minutes)
            st.metric("Estimated burn", f"{burn:,} kcal",
                      help=f"{met:g} MET x {latest_weight:.1f} kg x {minutes / 60:.2f} hours")
            if st.button("Add workout", type="primary"):
                storage.append_rows("workout_log", folder, [{
                    "Date": pd.Timestamp(workout_day), "Workout": kind,
                    "Duration_min": minutes, "Calories_Burned": burn,
                }])
                done(f"Added {kind.lower()} on {pd.Timestamp(workout_day):%d %b}")

        st.subheader("Recent workouts")
        deletable_table(
            "workout_log", workouts.sort_values("Date", ascending=False).head(10),
            ["Date", "Workout", "Duration_min", "Calories_Burned"],
            {"Date": st.column_config.DateColumn(format="DD MMM YYYY"),
             "Duration_min": st.column_config.NumberColumn("Minutes", format="%d"),
             "Calories_Burned": st.column_config.NumberColumn("Burned (kcal)", format="%.0f")},
            key="workout_table",
        )

# ------------------------------------------------------------- Progress tab

with tab_progress:
    if daily.empty:
        st.info("Nothing logged yet. Add food on the Today tab, or switch on "
                "**Use demo data** in the sidebar to see how the charts look.")
    else:
        periods = {"Last 7 days": 7, "Last 14 days": 14, "Last 30 days": 30, "All time": None}
        period = st.radio("Period", list(periods), index=2, horizontal=True)
        view = calc.window(daily, anchor, periods[period])
        stats = calc.kpis(view)

        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Average eaten per day",
                  f"{stats['avg_intake']:,.0f} kcal" if stats["avg_intake"] else "–",
                  help="Average over the days you logged food.")
        k2.metric("Average net per day",
                  f"{stats['avg_net']:,.0f} kcal" if stats["avg_net"] else "–",
                  help="Calories eaten minus calories burned in workouts.")
        k3.metric("Days within budget", f"{stats['days_within']} of {stats['days_logged']}",
                  help="Ate within 10% of the day's budget.")
        k4.metric("Average protein per day",
                  f"{stats['avg_protein']:.0f} g" if stats["avg_protein"] else "–")
        k5.metric("Current weight",
                  f"{stats['latest_weight']:.1f} kg" if stats["latest_weight"] else "–",
                  delta=f"{stats['weight_change']:+.1f} kg" if stats["weight_change"] is not None else None,
                  delta_color="off",
                  help="Latest weigh-in. The small number is the change since the first weigh-in in this period.")

        trend = calc.weight_trend(view, profile["goal_weight_kg"])
        in_window = workouts[(workouts["Date"] >= view.index.min()) & (workouts["Date"] <= view.index.max())]
        totals = calc.workout_totals(in_window)

        st.pyplot(charts.fig_calories(view))
        st.pyplot(charts.fig_weight(view, trend, profile["goal_weight_kg"]))
        if trend is not None:
            st.info(trend["message"])
        else:
            st.caption("A weight trend needs at least 5 weigh-ins spread over a week or more.")

        left_col, right_col = st.columns(2, gap="large")
        with left_col:
            st.pyplot(charts.fig_workouts(totals))
        with right_col:
            st.pyplot(charts.fig_energy_split(calc.energy_split(view)))

        with st.expander("Weekly summary"):
            st.dataframe(calc.weekly_summary(daily).iloc[::-1])
        with st.expander("Daily table"):
            st.dataframe(view.drop(columns=["Weight_used"]).round(1).iloc[::-1])

        snapshot = day_snapshot(anchor)
        png = dashboard_png(view, trend, profile["goal_weight_kg"], totals,
                            snapshot["consumed"], snapshot["targets"],
                            f"{profile['goal']}  ·  {period.lower()}")
        st.download_button("Download dashboard as PNG", data=png,
                           file_name="fitness_dashboard.png", mime="image/png")
