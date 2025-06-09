import streamlit as st
import pandas as pd
import calendar
from datetime import datetime
import random

st.set_page_config(page_title="Doula On-Call Scheduler", layout="wide")

if "submissions" not in st.session_state:
    st.session_state.submissions = []

st.title("Doula On-Call Scheduler")

menu = st.sidebar.selectbox("Menu", ["Submit Availability", "Admin Dashboard"])

def am_pm_options(month, num_days):
    # Returns options like "Jun 1 AM", "Jun 1 PM", ...
    return [f"{month[:3]} {i} AM" for i in range(1, num_days + 1)] + [f"{month[:3]} {i} PM" for i in range(1, num_days + 1)]

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
        admin_assigned = st.multiselect("Dates Already Assigned as Admin", options=day_options, key="admin_days")
        admin_available = st.multiselect("Dates Available for Admin", options=day_options, key="admin_avail")
        best_dates = st.multiselect("Best Dates to Be On Call (AM/PM)", options=am_pm_options(month, num_days), key="best_dates")

        submitted = st.form_submit_button("Submit")
        if submitted and name:
            st.session_state.submissions.append({
                "name": name,
                "births": int(births),
                "month": month,
                "year": year,
                "unavailable": unavailable_dates,
                "admin_assigned": admin_assigned,
                "admin_available": admin_available,
                "best_dates": best_dates
            })
            st.success("Availability submitted successfully!")
            st.rerun()

def scheduler(submissions, month, year):
    # Extract data
    doulas = sorted({s["name"] for s in submissions if s["month"] == month and s["year"] == year})
    if not doulas:
        return None, None

    # Requested and constraint fields
    requested = {s["name"]: s["births"] for s in submissions if s["month"] == month and s["year"] == year}
    unavailable = {s["name"]: set(s["unavailable"]) for s in submissions if s["month"] == month and s["year"] == year}
    admin_assigned = {s["name"]: set(s.get("admin_assigned", [])) for s in submissions if s["month"] == month and s["year"] == year}
    admin_available = {s["name"]: set(s.get("admin_available", [])) for s in submissions if s["month"] == month and s["year"] == year}
    best_dates = {s["name"]: set(s.get("best_dates", [])) for s in submissions if s["month"] == month and s["year"] == year}

    num_days = calendar.monthrange(year, list(calendar.month_name).index(month))[1]
    date_list = [datetime(year, list(calendar.month_name).index(month), day) for day in range(1, num_days + 1)]
    day_labels = [f"{month[:3]} {d.day}" for d in date_list]

    # Proportional target logic as before
    total_shifts = num_days * 4
    total_requested_births = sum(requested.values())
    proportional_target = {}
    for name in doulas:
        if total_requested_births > 0:
            proportional_target[name] = round((requested[name] / total_requested_births) * total_shifts)
        else:
            proportional_target[name] = 0

    # Tracking assignments and eligibility
    assigned_count = {name: 0 for name in doulas}
    assigned_rank_count = {name: [0,0,0,0] for name in doulas}
    last_assignment = {name: {"rank": None, "day": -3} for name in doulas}
    # Track for new rules: who was 3rd/admin yesterday
    third_yesterday = set()
    admin_yesterday = set()

    schedule = pd.DataFrame(index=day_labels, columns=["1st On Call", "2nd On Call", "3rd On Call", "Admin"])

    for day_idx, date in enumerate(date_list):
        day_label = f"{month[:3]} {date.day}"
        assigned_today = []
        # Rule: prioritize filling 1st and 2nd on call

        for rank in range(1, 5):
            # ADMIN = rank 4
            label = "Admin" if rank == 4 else f"{rank}st On Call" if rank == 1 else f"{rank}nd On Call" if rank == 2 else "3rd On Call"

            candidates = []
            for name in doulas:
                # Base exclusions
                if (
                    name in assigned_today
                    or day_label in unavailable[name]
                ):
                    continue

                # Rule: no consecutive days, UNLESS assigned 3rd (for any shift)
                prev_rank = last_assignment[name]["rank"]
                prev_day = last_assignment[name]["day"]
                can_be_today = False
                if day_idx - prev_day > 1:
                    can_be_today = True
                elif day_idx - prev_day == 1:
                    # Consecutive days only allowed if 3rd on call yesterday
                    if prev_rank == 3:
                        can_be_today = True
                else:
                    can_be_today = False

                # If assigning Admin, only pick from "available for admin" and not already admin assigned elsewhere
                if rank == 4:
                    if (day_label not in admin_available[name]) or (day_label in admin_assigned[name]):
                        continue

                # Rule: If assigning Admin as fallback for 3rd, do NOT assign to someone who was 1st or 2nd yesterday
                if rank == 3:
                    if (len(doulas) < 3 or name in assigned_today):  # Fallback scenario
                        prev_rank = last_assignment[name]["rank"]
                        prev_day = last_assignment[name]["day"]
                        if prev_rank in [1,2] and day_idx - prev_day == 1:
                            continue

                # Rule: avoid (but allow if needed) consecutive 2nd or 3rd assignments
                if rank in [2,3] and day_idx - prev_day == 1 and prev_rank == rank:
                    # Lower priority, but not excluded
                    pass

                # If best dates exist, prioritize them for on call
                if label != "Admin" and best_dates[name]:
                    best_label_am = f"{day_label} AM"
                    best_label_pm = f"{day_label} PM"
                    if best_label_am in best_dates[name] or best_label_pm in best_dates[name]:
                        candidates.append((name, True))
                        continue

                if can_be_today:
                    candidates.append((name, False))

            # If no candidates for 3rd, try admin (fallback, avoid repeat 1st/2nd as per rule)
            if rank == 3 and not candidates:
                label = "Admin"
                for name in doulas:
                    prev_rank = last_assignment[name]["rank"]
                    prev_day = last_assignment[name]["day"]
                    if (
                        name not in assigned_today
                        and day_label not in unavailable[name]
                        and day_label in admin_available[name]
                        and can_be_today
                    ):
                        if not (prev_rank in [1,2] and day_idx - prev_day == 1):
                            candidates.append((name, False))

            if not candidates:
                continue

            # Prioritize best dates
            if any(is_best for _, is_best in candidates):
                best_candidates = [n for n, is_best in candidates if is_best]
            else:
                # For all, pick furthest below proportional target, then random
                min_gap = min([proportional_target[n] - assigned_count[n] for n, _ in candidates])
                best_candidates = [n for n, _ in candidates if proportional_target[n] - assigned_count[n] == min_gap]

            chosen = random.choice(best_candidates)
            schedule.iloc[day_idx, rank-1] = chosen
            assigned_count[chosen] += 1
            assigned_rank_count[chosen][rank-1] += 1
            assigned_today.append(chosen)
            last_assignment[chosen] = {"rank": rank, "day": day_idx}

            if rank == 3:
                third_yesterday = set([chosen])
            if label == "Admin":
                admin_yesterday = set([chosen])

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
            sched, counts = scheduler(submissions, sel_month, sel_year)
            if sched is None:
                st.warning("No submissions for selected month/year.")
            else:
                st.subheader("Optimized Schedule")
                st.dataframe(sched)
                csv_sched = sched.to_csv().encode("utf-8")
                st.download_button("Download Schedule as CSV", csv_sched, "schedule.csv", "text/csv")
