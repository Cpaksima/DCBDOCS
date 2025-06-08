
import streamlit as st
import pandas as pd
import calendar
from datetime import datetime, timedelta
import random

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

def balanced_schedule(submissions, month, year):
    doulas = sorted({s["name"] for s in submissions if s["month"] == month and s["year"] == year})
    if not doulas:
        return None, None
    requested = {s["name"]: s["births"] for s in submissions if s["month"] == month and s["year"] == year}
    unavailable = {s["name"]: set(s["unavailable"]) | set(s["admin_days"]) for s in submissions if s["month"] == month and s["year"] == year}
    num_days = calendar.monthrange(year, list(calendar.month_name).index(month))[1]
    date_list = [datetime(year, list(calendar.month_name).index(month), day) for day in range(1, num_days + 1)]
    day_labels = [f"{month[:3]} {d.day}" for d in date_list]
    schedule = pd.DataFrame(index=day_labels, columns=[f"{i}st On Call" if i==1 else f"{i}nd On Call" if i==2 else f"{i}rd On Call" if i==3 else f"{i}th On Call" for i in range(1,5)])

    # Track assignments
    assigned_count = {name: 0 for name in doulas}
    assigned_rank_count = {name: [0,0,0,0] for name in doulas}
    last_assigned_day = {name: -3 for name in doulas}  # will store last day index assigned (so -3 allows assignment on first day)

    # Build the full schedule for each day, each rank
    # Pass 1: Assign 1st On Call by requested births, enforcing non-consecutive and availability
    for day_idx, date in enumerate(date_list):
        candidates = []
        for name in doulas:
            day_label = f"{month[:3]} {date.day}"
            if (
                assigned_count[name] < requested.get(name, 0)
                and assigned_rank_count[name][0] < requested.get(name, 0)
                and day_label not in unavailable[name]
                and day_idx - last_assigned_day[name] > 1
            ):
                candidates.append(name)
        # If not enough, consider anyone who is available and hasn't done 1st On Call the day before
        if not candidates:
            for name in doulas:
                day_label = f"{month[:3]} {date.day}"
                if (
                    day_label not in unavailable[name]
                    and day_idx - last_assigned_day[name] > 1
                ):
                    candidates.append(name)
        # Pick least used, then random for fairness
        if candidates:
            min_used = min([assigned_count[n] for n in candidates])
            min_candidates = [n for n in candidates if assigned_count[n]==min_used]
            chosen = random.choice(min_candidates)
            schedule.iloc[day_idx, 0] = chosen
            assigned_count[chosen] += 1
            assigned_rank_count[chosen][0] += 1
            last_assigned_day[chosen] = day_idx

    # Pass 2–4: Assign 2nd, 3rd, 4th On Call (cannot repeat any doula that day, not consecutive, not unavailable, spread evenly)
    for rank in range(2, 5):
        for day_idx, date in enumerate(date_list):
            already = [schedule.iloc[day_idx, r] for r in range(rank-1)]
            candidates = []
            for name in doulas:
                day_label = f"{month[:3]} {date.day}"
                if (
                    name not in already
                    and day_label not in unavailable[name]
                    and day_idx - last_assigned_day.get((name, rank), -3) > 1
                ):
                    candidates.append(name)
            if candidates:
                # Spread as evenly as possible
                count_for_rank = [assigned_rank_count[n][rank-1] for n in candidates]
                min_count = min(count_for_rank)
                min_candidates = [n for n in candidates if assigned_rank_count[n][rank-1] == min_count]
                chosen = random.choice(min_candidates)
                schedule.iloc[day_idx, rank-1] = chosen
                assigned_rank_count[chosen][rank-1] += 1
                last_assigned_day[(chosen, rank)] = day_idx

    return schedule, assigned_rank_count

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
            sched, counts = balanced_schedule(submissions, sel_month, sel_year)
            if sched is None:
                st.warning("No submissions for selected month/year.")
            else:
                st.subheader("Optimized Schedule")
                st.dataframe(sched)
                csv_sched = sched.to_csv().encode("utf-8")
                st.download_button("Download Schedule as CSV", csv_sched, "schedule.csv", "text/csv")
