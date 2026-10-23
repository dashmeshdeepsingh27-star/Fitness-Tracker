"""All the matplotlib charts.

Every plot_* function draws onto an Axes you hand it, so the same code serves
both a single chart on the page and the four-panel dashboard. The fig_*
functions wrap them into ready-to-show figures.

Figures are built with matplotlib's Figure class directly (not pyplot), so
Streamlit reruns never pile up open figures in memory.

Colours follow one rule: they say what a mark *means*, not how big it is.
Blue = on target, light blue = under, orange = over. The three series colours
were checked for colour-blind separation.
"""

import io

import matplotlib
import matplotlib.dates as mdates
import numpy as np
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter

matplotlib.rcParams["font.family"] = "sans-serif"
matplotlib.rcParams["font.sans-serif"] = ["Segoe UI", "Helvetica Neue", "Arial", "DejaVu Sans"]

# surface and ink
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"

# series colours
BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"
BLUE_LIGHT = "#86b6ef"
BLUE_DARK = "#184f95"
BLUE_TRACK = "#cde2fb"

DPI = 144

# For these nutrients, reaching the target is the aim; for the rest it is a limit.
GOALS_TO_REACH = {"Proteins", "Fibre"}


# ----------------------------------------------------------------- helpers

def _compact(value, _pos=None):
    """0 / 500 / 1K / 1.5K / 2K for axis ticks."""
    return f"{value / 1000:g}K" if abs(value) >= 1000 else f"{value:g}"


def _prepare(ax, title):
    """Quiet chart chrome: no box, hairline grid, muted text."""
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.tick_params(colors=MUTED, labelsize=8.5, length=0)
    ax.tick_params(axis="x", length=3, color=AXIS)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_title(title, loc="left", color=INK, fontsize=11, fontweight="bold", pad=8)


def _empty(ax, title, message):
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", color=INK, fontsize=11, fontweight="bold", pad=8)
    ax.text(0.5, 0.5, message, transform=ax.transAxes, ha="center", va="center",
            color=MUTED, fontsize=10)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)


def _legend(ax, handles, ncol):
    """Legend under the plot, no frame."""
    legend = ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(0, -0.12),
                       ncol=ncol, frameon=False, fontsize=8.5, handlelength=1.4,
                       columnspacing=1.4, borderaxespad=0)
    for text in legend.get_texts():
        text.set_color(INK_2)


def _date_axis(ax, x):
    """Date ticks with a little room on the right for an end label."""
    span = max(float(x[-1] - x[0]), 1.0)
    ax.set_xlim(x[0] - 0.8, x[-1] + max(1.2, 0.08 * span))
    ax.xaxis_date()
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3, maxticks=7))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))


def _end_label(ax, x, y, text):
    ax.annotate(text, (x, y), xytext=(6, 0), textcoords="offset points",
                va="center", fontsize=8.5, color=INK)


def _new_figure(width, height):
    fig = Figure(figsize=(width, height), dpi=DPI, layout="constrained")
    fig.patch.set_facecolor(SURFACE)
    return fig


def figure_to_png(fig):
    """PNG bytes of a figure, for a download button."""
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", facecolor=SURFACE)
    return buffer.getvalue()


# --------------------------------------------------------------- the charts

def plot_calories(ax, df):
    """Daily intake as bars coloured by status, with the budget and 7-day average."""
    title = "Calories eaten vs budget"
    if df["Intake"].notna().sum() == 0:
        _empty(ax, title, "No food logged in this period")
        return

    _prepare(ax, title)
    x = mdates.date2num(df.index)
    intake = df["Intake"].fillna(0).to_numpy()

    status = df["Status"].to_numpy()
    colour = np.select(
        [status == "Within", status == "Under", status == "Over", status == "In progress"],
        [BLUE, BLUE_LIGHT, ORANGE, AXIS],
        default=SURFACE,                       # "No data" days draw nothing
    )
    width = 0.72 if len(x) > 14 else 0.5          # keep bars slim in short windows
    ax.bar(x, intake, width=width, color=colour, edgecolor=SURFACE, linewidth=1, zorder=2)
    ax.step(x, df["Budget"].to_numpy(), where="mid", color=MUTED, linewidth=1.5, zorder=3)

    average = df["Intake_7d"]
    ax.plot(x, average.to_numpy(), color=INK, linewidth=2, solid_capstyle="round", zorder=4)
    last = average.last_valid_index()
    if last is not None:
        _end_label(ax, mdates.date2num(last), average[last], f"{average[last]:,.0f}")

    top = max(np.nanmax(intake), np.nanmax(df["Budget"].to_numpy()))
    ax.set_ylim(0, top * 1.1)
    ax.yaxis.set_major_formatter(FuncFormatter(_compact))
    _date_axis(ax, x)

    labels = {
        "Within": ("Within 10% of budget", BLUE),
        "Under": ("Under budget", BLUE_LIGHT),
        "Over": ("Over budget", ORANGE),
        "In progress": ("Today so far", AXIS),
    }
    handles = [Patch(facecolor=colour_, label=label)
               for key, (label, colour_) in labels.items() if (status == key).any()]
    handles.append(Line2D([], [], color=MUTED, linewidth=1.5, label="Budget (target + workouts)"))
    handles.append(Line2D([], [], color=INK, linewidth=2, label="7-day average"))
    _legend(ax, handles, ncol=3)


def plot_weight(ax, df, trend, goal_weight):
    """Weigh-ins, their 7-day average, the fitted trend and the goal."""
    title = "Body weight (kg)"
    weigh_ins = df["Weight"].dropna()
    if weigh_ins.empty:
        _empty(ax, title, "Log a weigh-in to see this chart")
        return

    _prepare(ax, title)
    x = mdates.date2num(df.index)
    handles = []

    ax.scatter(mdates.date2num(weigh_ins.index), weigh_ins.to_numpy(), s=42, color=BLUE,
               edgecolor=SURFACE, linewidth=1.5, zorder=4)
    handles.append(Line2D([], [], marker="o", linestyle="", color=BLUE, markersize=6,
                          label="Weigh-in"))

    average = df["Weight_7d"].dropna()
    ax.plot(mdates.date2num(average.index), average.to_numpy(), color=BLUE_DARK, linewidth=2,
            solid_capstyle="round", zorder=3)
    handles.append(Line2D([], [], color=BLUE_DARK, linewidth=2, label="7-day average"))
    _end_label(ax, mdates.date2num(average.index[-1]), average.iloc[-1], f"{average.iloc[-1]:.1f}")

    low, high = weigh_ins.min(), weigh_ins.max()
    if trend is not None:
        ax.plot(mdates.date2num([trend["x_start"], trend["x_end"]]),
                [trend["y_start"], trend["y_end"]], color=ORANGE, linewidth=2,
                linestyle=(0, (5, 3)), zorder=2)
        handles.append(Line2D([], [], color=ORANGE, linewidth=2, linestyle=(0, (5, 3)),
                              label=f"Trend ({trend['per_week']:+.2f} kg/week)"))

    # only draw the goal line if it is close enough not to flatten the data
    if low - 3 <= goal_weight <= high + 3:
        ax.axhline(goal_weight, color=MUTED, linewidth=1.3, zorder=1)
        handles.append(Line2D([], [], color=MUTED, linewidth=1.3, label=f"Goal ({goal_weight:g} kg)"))
        low, high = min(low, goal_weight), max(high, goal_weight)

    ax.set_ylim(low - 0.6, high + 0.6)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    _date_axis(ax, x)
    _legend(ax, handles, ncol=2)


def plot_workouts(ax, totals):
    """Calories burned per workout type."""
    title = "Calories burned by workout"
    if totals.empty:
        _empty(ax, title, "No workouts logged in this period")
        return

    # keep the chart readable: top 6 types, everything else folded into "Other"
    if len(totals) > 7:
        other = totals.iloc[6:].sum()
        totals = totals.iloc[:6].copy()
        totals.loc["Other"] = other

    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", color=INK, fontsize=11, fontweight="bold", pad=8)
    burned = totals["Calories_Burned"].to_numpy()
    positions = np.arange(len(totals))

    ax.barh(positions, burned, height=0.5, color=BLUE, edgecolor=SURFACE, linewidth=1)
    for pos, kcal, minutes in zip(positions, burned, totals["Duration_min"].to_numpy()):
        ax.annotate(f"{kcal:,.0f} kcal  ·  {minutes:,.0f} min", (kcal, pos),
                    xytext=(6, 0), textcoords="offset points", va="center",
                    fontsize=8.5, color=INK_2)

    ax.set_yticks(positions, labels=totals.index)
    ax.invert_yaxis()
    ax.set_xlim(0, burned.max() * 1.65)
    ax.set_xticks([])
    ax.tick_params(axis="y", colors=INK_2, labelsize=9, length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)


def plot_macros(ax, consumed, targets):
    """Consumed vs target as meters. Both arguments are dicts keyed by nutrient."""
    title = "Today vs target"
    rows = [("Calories", "Calories", "kcal"), ("Proteins", "Protein", "g"),
            ("Carbs", "Carbs", "g"), ("Fat", "Fat", "g"), ("Fibre", "Fibre", "g")]

    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", color=INK, fontsize=11, fontweight="bold", pad=8)
    positions = np.arange(len(rows))

    for pos, (key, _label, unit) in zip(positions, rows):
        share = consumed[key] / targets[key] if targets[key] else 0.0
        # going past a limit (calories, carbs, fat) is a warning; past a goal (protein, fibre) is fine
        over_limit = share > 1 and key not in GOALS_TO_REACH
        ax.barh(pos, 100, height=0.42, color=BLUE_TRACK)
        ax.barh(pos, min(share, 1.0) * 100, height=0.42, color=ORANGE if over_limit else BLUE)
        note = f"{consumed[key]:,.0f} / {targets[key]:,.0f} {unit}"
        if over_limit:
            note += "  (over)"
        elif share >= 1:
            note += "  (reached)"
        ax.annotate(note, (100, pos), xytext=(8, 0), textcoords="offset points",
                    va="center", fontsize=8.5, color=INK_2)

    ax.set_yticks(positions, labels=[label for _key, label, _unit in rows])
    ax.invert_yaxis()
    ax.set_xlim(0, 175)
    ax.set_xticks([])
    ax.tick_params(axis="y", colors=INK_2, labelsize=9, length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)


def plot_energy_split(ax, split):
    """One 100% bar: share of calories from protein, carbs and fat."""
    title = "Where your calories come from"
    if split is None:
        _empty(ax, title, "No food logged in this period")
        return

    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", color=INK, fontsize=11, fontweight="bold", pad=8)
    colours = {"Protein": BLUE, "Carbs": ORANGE, "Fat": AQUA}

    left = 0.0
    handles = []
    for name, share in split.items():
        ax.barh(0, share, left=left, height=0.5, color=colours[name], edgecolor=SURFACE,
                linewidth=2)
        left += share
        handles.append(Patch(facecolor=colours[name], label=f"{name} {share:.0f}%"))

    ax.set_xlim(0, 100)
    ax.set_ylim(-0.6, 0.6)
    ax.axis("off")
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(0, 0.1), ncol=3,
              frameon=False, fontsize=9, labelcolor=INK_2, handlelength=1.4, borderaxespad=0)


# ------------------------------------------------------------ ready figures

def fig_calories(df):
    fig = _new_figure(7.2, 3.9)
    plot_calories(fig.subplots(), df)
    return fig


def fig_weight(df, trend, goal_weight):
    fig = _new_figure(7.2, 3.9)
    plot_weight(fig.subplots(), df, trend, goal_weight)
    return fig


def fig_workouts(totals):
    fig = _new_figure(5.0, 3.3)
    plot_workouts(fig.subplots(), totals)
    return fig


def fig_macros(consumed, targets):
    fig = _new_figure(5.0, 3.3)
    plot_macros(fig.subplots(), consumed, targets)
    return fig


def fig_energy_split(split):
    fig = _new_figure(5.0, 1.6)
    plot_energy_split(fig.subplots(), split)
    return fig


def fig_dashboard(df, trend, goal_weight, totals, consumed, targets, heading):
    """The four-panel overview, sized for a slide."""
    fig = _new_figure(13.0, 8.4)
    (top_left, top_right), (bottom_left, bottom_right) = fig.subplots(2, 2)
    fig.suptitle(heading, x=0.01, ha="left", fontsize=14, fontweight="bold", color=INK)
    plot_calories(top_left, df)
    plot_weight(top_right, df, trend, goal_weight)
    plot_workouts(bottom_left, totals)
    plot_macros(bottom_right, consumed, targets)
    return fig
