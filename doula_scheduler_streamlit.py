import streamlit as st
import pandas as pd
import calendar
from datetime import datetime, timedelta
import random
import math

st.set_page_config(page_title="Doula On-Call Scheduler", layout="wide")

if "submissions" not in st.session_state:
    st.session_state.submissions = []

st.title("Doula On-Call Scheduler")

menu = st.sidebar.selectbox("Menu", ["Submit Availability", "Admin Dashboard"])

if menu == "Submit Availability":
    st.header("Doula Availability Submission Form")
    with st.form("doula_form", clear_on_submit=True):
        name = st.text_input("Doula Full Name", key="name")
        births = st.number_input("Requested Number of Births", min_value=0, max_value=31, value=4, key="births")
        month = st.selectbox("Select Month", list(calendar.month_name)[1:], index=datetime.now().month-1, key="form_month")
        year = st.selectbox("Select Year", list(range(datetime.now().year, datetime.now().year + 3)), index=0, key="form_year")
        num_days = calendar.monthrange(year, list(calendar.month_name).index(month))[1]
        day_options = [f"{month[:3]} {i}" for i in range(1, num_days + 1)]
        unavailable_dates = st.multiselect("Unavailable Dates", options=day_options, key="unavailable")
        admin_days = st.multiselect("Admin Assigned Days", options=day_options, key="admin_days")
        submitted = st.form_submit_button("Submit")

        if submitted and name:
            st.session_state.submissions.append({
                "name": name,
                "births": int(births),
                "month": month,
                "year": year,
                "unavailable": unavailable_dates,
                "admin_days": admin_days
            })
            st.success("Availability submitted successfully!")
            st.rerun()

def proportional_balanced_schedule(submissions, month, year):
    doulas = sorted({s["name"] for s in submissions if s["month"] == month and s["year"] == year})
    if not doulas:
        return None, None, None
    requested = {s["name"]: s["births"] for s in submissions if s["month"] == month and s["year"] == year}
    unavailable = {s["name"]: set(s["unavailable"]) | set(s["admin_days"]) for s in submissions if s["month"] == month and s["year"] == year}
    num_days = calendar.monthrange(year, list(calendar.month_name).index(month))[1]
    total_shifts = num_days * 4
    total_requested_births = sum(requested.values())

    # Proportional shifts target for each doula
    proportional_target = {}
    for name in doulas:
        if total_requested_births > 0:
            proportional_target[name] = round((requested[name] / total_requested_births) * total_shifts)
        else:
            proportional_target[name] = 0

    date_list = [datetime(year, list(calendar.month_name).index(month), day) for day in range(1, num_days + 1)]
    day_labels = [f"{month[:3]} {d.day}" for d in date_list]
    schedule = pd.DataFrame(index=day_labels, columns=[f"{i}st On Call" if i==1 else f"{i}nd On Call" if i==2 else f"{i}rd On Call" if i==3 else f"{i}th On Call" for i in range(1,5)])

    assigned_count = {name: 0 for name in doulas}  # Total shifts
    assigned_rank_count = {name: [0,0,0,0] for name in doulas}
    last_assigned_day = {name: -3 for name in doulas}
    fourth_on_call_yesterday = set()

    for day_idx, date in enumerate(date_list):
        ineligible_today = set(fourth_on_call_yesterday)
        fourth_on_call_yesterday = set()

        assigned_today = []
        for rank in range(1,5):
            candidates = []
            for name in doulas:
                day_label = f"{month[:3]} {date.day}"
                if (
                    name not in assigned_today
                    and day_label not in unavailable[name]
                    and name not in ineligible_today
                ):
                    # Enforce no consecutive days for any rank
                    if rank == 1:
                        if day_idx - last_assigned_day[name] > 1:
                            candidates.append(name)
                    else:
                        if day_idx - last_assigned_day.get((name, rank), -3) > 1:
                            candidates.append(name)
            # Proportional balancing: among candidates, prefer doulas furthest *below* their proportional target
            if candidates:
                gap = [(name, proportional_target[name] - assigned_count[name]) for name in candidates]
                max_gap = max([g for n, g in gap])
                best_candidates = [n for n, g in gap if g == max_gap]
                chosen = random.choice(best_candidates)
                schedule.iloc[day_idx, rank-1] = chosen
                assigned_count[chosen] += 1
                assigned_rank_count[chosen][rank-1] += 1
                if rank == 1:
                    last_assigned_day[chosen] = day_idx
                else:
                    last_assigned_day[(chosen, rank)] = day_idx
                assigned_today.append(chosen)
                if rank == 4:
                    fourth_on_call_yesterday = set([chosen])

    return schedule, assigned_rank_count, proportional_target

if menu == "Admin Dashboard":
    st.header("Admin Dashboard")
    submissions = st.session_state.get("submissions", [])
    if not submissions:
        st.info("No doula submissions yet.")
    else:
        df = pd.DataFrame(submissions)
        st.dataframe(df)
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("Download All Submissions as CSV", csv, "submissions.csv", "text/csv")
        summary = df.groupby("name")["births"].sum().reset_index()
        st.subheader("Total Requested Assignments by Doula")
        st.dataframe(summary)

        months = sorted(df["month"].unique(), key=lambda m: list(calendar.month_name).index(m))
        years = sorted(df["year"].unique())
        sel_month = st.selectbox("Generate Schedule for Month", months, key="admin_month")
        sel_year = st.selectbox("Year", years, key="admin_year")
        if st.button("Generate Optimized Schedule"):
            sched, counts, proportional_target = proportional_balanced_schedule(submissions, sel_month, sel_year)
            if sched is None:
                st.warning("No submissions for selected month/year.")
            else:
                st.subheader("Optimized Schedule")
                st.dataframe(sched)
                # Show each doula's actual vs. target shifts
                actual_shifts = {name: sum(v) for name, v in counts.items()}
                comparison_df = pd.DataFrame({
                    "Doula": list(proportional_target.keys()),
                    "Target Shifts": [proportional_target[n] for n in proportional_target],
                    "Actual Shifts": [actual_shifts[n] for n in proportional_target],
                    "1st On Call": [counts[n][0] for n in proportional_target],
                    "2nd On Call": [counts[n][1] for n in proportional_target],
                    "3rd On Call": [counts[n][2] for n in proportional_target],
                    "4th On Call": [counts[n][3] for n in proportional_target],
                })
                st.subheader("Shift Assignment Comparison")
                st.dataframe(comparison_df)
                csv_sched = sched.to_csv().encode("utf-8")
                st.download_button("Download Schedule as CSV", csv_sched, "schedule.csv", "text/csv")
