import streamlit as st
import pandas as pd
import calendar
from datetime import datetime, timedelta
import random

[theme]
primaryColor="#ffffff"  # Example primary color
backgroundColor="#000000"  # Example background color
secondaryBackgroundColor="#f9f7f3"  # Example secondary background color
textColor="#3f4e63"  # Example text color

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

    assigned_count = {name: 0 for name in doulas}
    assigned_rank_count = {name: [0,0,0,0] for name in doulas}
    last_assigned_day = {name: -3 for name in doulas}
    # Track for the new rule: who was 4th on call yesterday
    fourth_on_call_yesterday = set()

    for day_idx, date in enumerate(date_list):
        # Build a set of doulas ineligible today due to being 4th on call yesterday
        ineligible_today = set(fourth_on_call_yesterday)
        fourth_on_call_yesterday = set()  # Will update this at the end of today's assignments

        # Assign each on-call position (1st to 4th) for today
        assigned_today = []
        for rank in range(1,5):
            # Determine eligible doulas for this slot
            candidates = []
            for name in doulas:
                day_label = f"{month[:3]} {date.day}"
                # Exclude if assigned already today, unavailable, ineligible due to yesterday 4th-on-call, or for 1st slot, need to balance requested
                if (
                    name not in assigned_today
                    and day_label not in unavailable[name]
                    and name not in ineligible_today
                ):
                    # For 1st slot, try to hit requested number (then overflow if needed)
                    if rank == 1:
                        if assigned_count[name] < requested.get(name, 0) and assigned_rank_count[name][0] < requested.get(name, 0) and day_idx - last_assigned_day[name] > 1:
                            candidates.append(name)
                    else:
                        # For 2nd-4th, cannot be assigned same person as any earlier slot today and not on consecutive days for this rank
                        if day_idx - last_assigned_day.get((name, rank), -3) > 1:
                            candidates.append(name)

            # If not enough for 1st slot, allow overflow (just need not ineligible, not assigned today, not unavailable, not consecutive)
            if rank == 1 and not candidates:
                for name in doulas:
                    day_label = f"{month[:3]} {date.day}"
                    if (
                        name not in assigned_today
                        and day_label not in unavailable[name]
                        and name not in ineligible_today
                        and day_idx - last_assigned_day[name] > 1
                    ):
                        candidates.append(name)

            # If still empty, leave blank (shouldn't happen unless all doulas unavailable)
            if not candidates:
                continue

            # Choose among least-assigned for this rank, break ties randomly
            if rank == 1:
                min_used = min([assigned_count[n] for n in candidates])
                min_candidates = [n for n in candidates if assigned_count[n]==min_used]
                chosen = random.choice(min_candidates)
                assigned_count[chosen] += 1
                assigned_rank_count[chosen][0] += 1
                last_assigned_day[chosen] = day_idx
            else:
                count_for_rank = [assigned_rank_count[n][rank-1] for n in candidates]
                min_count = min(count_for_rank)
                min_candidates = [n for n in candidates if assigned_rank_count[n][rank-1] == min_count]
                chosen = random.choice(min_candidates)
                assigned_rank_count[chosen][rank-1] += 1
                last_assigned_day[(chosen, rank)] = day_idx

            schedule.iloc[day_idx, rank-1] = chosen
            assigned_today.append(chosen)

            # For 4th on call, remember for tomorrow's ineligibility
            if rank == 4:
                fourth_on_call_yesterday = set([chosen])

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
