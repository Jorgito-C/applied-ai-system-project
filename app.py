import streamlit as st
from datetime import date
from pawpal_system import Owner, Pet, Task, Scheduler

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")

# ── Session state bootstrap ───────────────────────────────────────────────────
# Streamlit reruns the entire script on every interaction, so we store the
# Owner object in st.session_state (a persistent dict) to avoid losing data.
# The "if not in" guard means we only create a fresh Owner on the very first
# run; every subsequent rerun reuses the same object already in the vault.
if "owner" not in st.session_state:
    st.session_state.owner = Owner(owner_id=1, name="", time_available=120)

if "next_pet_id" not in st.session_state:
    st.session_state.next_pet_id = 1

if "next_task_id" not in st.session_state:
    st.session_state.next_task_id = 1
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
            owner.add_pet(new_pet)                      # Owner.add_pet() stores it
            st.session_state.next_pet_id += 1
            st.success(f"Added {new_pet.name} the {new_pet.species}!")
        else:
            st.warning("Please enter a pet name.")

if owner.pets:
    st.write("**Your pets:**")
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
                due_time=due_time.strftime("%H:%M") if due_time else "08:00",
                frequency=frequency,
            )
            owner.add_task(new_task)                    # Owner.add_task() → pet.add_task()
            st.session_state.next_task_id += 1
            st.success(f"Added '{task_type}' for {target_pet.name} (priority {priority}, {duration} min).")

    all_tasks = owner.get_all_tasks()
    if all_tasks:
        st.write("**All tasks:**")
        st.table([
            {
                "Pet": t.pet.name,
                "Task": t.task_type,
                "Duration": t.duration,
                "Priority": t.priority,
                "Time": t.due_time,
                "Frequency": t.frequency,
                "Done": t.completed,
            }
            for t in all_tasks
        ])

st.divider()

# ── Section 4: Generate daily plan ───────────────────────────────────────────
st.subheader("Generate Daily Plan")

if st.button("Generate schedule"):
    all_tasks = owner.get_all_tasks()
    if not all_tasks:
        st.warning("No tasks to schedule. Add some tasks first.")
    else:
        scheduler = Scheduler(all_tasks)

        # Check for conflicts before showing the plan
        warnings = scheduler.get_conflict_warnings()
        if warnings:
            for w in warnings:
                st.warning(w)

        plan = scheduler.generate_daily_plan(time_available=owner.time_available)
        skipped = [t for t in scheduler.sort_tasks_by_priority() if t not in plan]

        st.success(f"Scheduled {len(plan)} task(s) within your {owner.time_available}-minute budget.")
        st.write("**Today's plan (highest priority first):**")
        for t in plan:
            st.markdown(
                f"- **{t.due_time}** — {t.task_type} for **{t.pet.name}** "
                f"({t.duration} min, priority {t.priority})"
            )

        if skipped:
            st.info(f"{len(skipped)} task(s) didn't fit in your time budget and were skipped:")
            for t in skipped:
                st.markdown(f"  - {t.task_type} for {t.pet.name} ({t.duration} min)")
