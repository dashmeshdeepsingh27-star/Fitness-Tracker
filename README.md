

**Count before you Eat**

A fitness tracker that turns daily logs into progress charts. You record what you eat, your weight and your workouts. The app works out a calorie budget from your body stats and goal, then shows how you are doing over time.

**What it does**

Logs food from a reference nutrition table, plus weight and workouts, into plain CSV files
Calculates a daily calorie target (Mifflin-St Jeor) and macro targets, and adds calories burned in workouts to the budget
Plots calories vs budget, weight with a 7-day rolling average and a fitted trend line, workout breakdowns and a four-panel dashboard
Projects the date you would reach your goal weight at your current rate
Includes a demo mode with 45 days of synthetic data, so you can see every chart without logging anything

Built with Python, pandas (groupby, rolling, resample, interpolate), numpy (polyfit, vectorised maths, random data generation), matplotlib and Streamlit.
