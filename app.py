import streamlit as st
from datetime import date
from pawpal_system import Owner, Pet, Task, Scheduler
from ai_planner import AgenticPlanner

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")

# ── Session state bootstrap ───────────────────────────────────────────────────
if "owner" not in st.session_state:
    st.session_state.owner = Owner(owner_id=1, name="", time_available=120)
if "next_pet_id" not in st.session_state:
    st.session_state.next_pet_id = 1
if "next_task_id" not in st.session_state:
    st.session_state.next_task_id = 1
if "ai_planner" not in st.session_state:
    st.session_state.ai_planner = AgenticPlanner()
# ─────────────────────────────────────────────────────────────────────────────

st.title("🐾 PawPal+")
owner: Owner = st.session_state.owner

# ── Section 1: Owner setup ────────────────────────────────────────────────────
st.subheader("Owner Setup")
with st.form("owner_form"):
    col1, col2 = st.columns(2)
    with col1:
        owner_name = st.text_input("Your name", value=owner.name or "")
    with col2:
        time_available = st.number_input(
            "Time available today (minutes)", min_value=10, max_value=480, value=owner.time_available
        )
    if st.form_submit_button("Save owner info"):
        owner.name = owner_name
        owner.time_available = time_available
        st.success(f"Saved! Hi {owner.name}, you have {owner.time_available} min today.")

st.divider()

# ── Section 2: Add a pet ──────────────────────────────────────────────────────
st.subheader("Add a Pet")
with st.form("add_pet_form"):
    col1, col2, col3 = st.columns(3)
    with col1:
        pet_name = st.text_input("Pet name")
    with col2:
        species = st.selectbox("Species", ["Dog", "Cat", "Other"])
    with col3:
        age = st.number_input("Age (years)", min_value=0, max_value=30, value=1)

    if st.form_submit_button("Add Pet"):
        if pet_name.strip():
            new_pet = Pet(
                pet_id=st.session_state.next_pet_id,
                name=pet_name.strip(),
                species=species,
                age=int(age),
            )
            owner.add_pet(new_pet)
            st.session_state.next_pet_id += 1
            st.success(f"Added {new_pet.name} the {new_pet.species}!")
        else:
            st.warning("Please enter a pet name.")

if owner.pets:
    st.table([{"Name": p.name, "Species": p.species, "Age": p.age} for p in owner.pets])
else:
    st.info("No pets added yet.")

st.divider()

# ── Section 3: Add a task ─────────────────────────────────────────────────────
st.subheader("Add a Care Task")

if not owner.pets:
    st.info("Add a pet first before scheduling tasks.")
else:
    with st.form("add_task_form"):
        pet_names = [p.name for p in owner.pets]
        col1, col2 = st.columns(2)
        with col1:
            selected_pet_name = st.selectbox("Assign to pet", pet_names)
            task_type = st.selectbox(
                "Task type", ["Walk", "Feeding", "Medication", "Grooming", "Enrichment", "Other"]
            )
            frequency = st.selectbox("Frequency", ["daily", "weekly", "once"])
        with col2:
            duration = st.number_input("Duration (minutes)", min_value=1, max_value=240, value=20)
            priority = st.slider("Priority (1 = low, 5 = high)", min_value=1, max_value=5, value=3)
            due_time = st.time_input("Due time", value=None)

        if st.form_submit_button("Add Task"):
            target_pet = next(p for p in owner.pets if p.name == selected_pet_name)
            new_task = Task(
                task_id=st.session_state.next_task_id,
                pet=target_pet,
                task_type=task_type,
                duration=int(duration),
                priority=priority,
                due_date=date.today(),
                due_time=due_time.strftime("%H:%M") if due_time else None,
                frequency=frequency,
            )
            owner.add_task(new_task)
            st.session_state.next_task_id += 1
            st.success(f"Added '{task_type}' for {target_pet.name} (priority {priority}, {duration} min).")

st.divider()

# ── Section 4: View & filter tasks ───────────────────────────────────────────
st.subheader("View Tasks")

all_tasks = owner.get_all_tasks()

if not all_tasks:
    st.info("No tasks yet. Add some above.")
else:
    scheduler = Scheduler(all_tasks)

    # Proactive conflict warnings — shown before anything else
    conflicts = scheduler.get_conflict_warnings()
    if conflicts:
        st.error(f"⚠️ {len(conflicts)} scheduling conflict(s) detected — two or more tasks share the same time slot. Reschedule one to avoid overlap.")
        for msg in conflicts:
            st.warning(msg)

    tab_time, tab_pet, tab_pending = st.tabs(["By Time", "Filter by Pet", "Pending Only"])

    with tab_time:
        sorted_by_time = scheduler.sort_tasks_by_time()
        st.caption("All tasks sorted chronologically.")
        st.table([
            {
                "Time": t.due_time or "Anytime",
                "Pet": t.pet.name,
                "Task": t.task_type,
                "Duration (min)": t.duration,
                "Priority": t.priority,
                "Frequency": t.frequency,
                "Done": "✅" if t.completed else "⬜",
            }
            for t in sorted_by_time
        ])

    with tab_pet:
        if owner.pets:
            selected = st.selectbox("Select a pet", [p.name for p in owner.pets], key="filter_pet")
            pet_tasks = scheduler.filter_tasks_by_pet(selected)
            if pet_tasks:
                st.caption(f"Showing {len(pet_tasks)} task(s) for {selected}.")
                st.table([
                    {
                        "Time": t.due_time,
                        "Task": t.task_type,
                        "Duration (min)": t.duration,
                        "Priority": t.priority,
                        "Done": "✅" if t.completed else "⬜",
                    }
                    for t in pet_tasks
                ])
            else:
                st.info(f"No tasks found for {selected}.")

    with tab_pending:
        pending = scheduler.filter_tasks_by_status(completed=False)
        if pending:
            st.caption(f"{len(pending)} task(s) still pending.")
            st.table([
                {
                    "Time": t.due_time,
                    "Pet": t.pet.name,
                    "Task": t.task_type,
                    "Duration (min)": t.duration,
                    "Priority": t.priority,
                }
                for t in pending
            ])
        else:
            st.success("All tasks are complete!")

st.divider()

# ── Section 5: Generate daily plan ───────────────────────────────────────────
st.subheader("Generate Daily Plan")

if st.button("Generate schedule"):
    all_tasks = owner.get_all_tasks()
    if not all_tasks:
        st.warning("No tasks to schedule. Add some tasks first.")
    else:
        scheduler = Scheduler(all_tasks)
        ai_result = st.session_state.ai_planner.plan_day(owner, all_tasks)
        plan = ai_result["plan"]
        skipped = ai_result["skipped"]

        minutes_used = sum(t.duration for t in plan)
        st.success(
            f"Scheduled {len(plan)} task(s) — {minutes_used} of {owner.time_available} min used."
        )

        for t in plan:
            st.markdown(
                f"**{t.due_time or 'Anytime'}** &nbsp;|&nbsp; {t.task_type} for **{t.pet.name}** "
                f"&nbsp;— {t.duration} min &nbsp;· priority {t.priority}"
            )

        if skipped:
            st.info(
                f"{len(skipped)} task(s) didn't fit in your {owner.time_available}-min budget and were skipped:"
            )
            for t in skipped:
                st.markdown(f"- {t.task_type} for {t.pet.name} ({t.duration} min, priority {t.priority})")

        st.caption(f"Planner source: {ai_result['source']}")
        if ai_result["notes"]:
            with st.expander("Planner notes and checks"):
                for note in ai_result["notes"]:
                    st.write(f"- {note}")
