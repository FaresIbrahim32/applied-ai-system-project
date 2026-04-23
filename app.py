import streamlit as st
from datetime import datetime, date, time, timedelta
from rag_engine import init_vectorstore, ask_rag





from pawpal_system import (
    AdoptionStatus,
    CarePlan,
    Pet,
    PetOwner,
    CareProvider,
    Appointment,
    AppointmentType,
    AppointmentStatus,
    Medication,
    CareClinic,
    SpeciesCategory,
    Task,
    TaskType,
    TimeSlot,
    WeeklySchedule,
)

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")


def safe_rerun():
    """Attempt to rerun the Streamlit script in a few different ways.

    Some Streamlit versions expose `st.experimental_rerun()`. Others require
    raising the internal `RerunException`. If neither is available, set a
    small session flag and ask the user to refresh manually.
    """
    try:
        if hasattr(st, "experimental_rerun"):
            st.experimental_rerun()
            return
    except Exception:
        pass
    try:
        # internal API used by some Streamlit versions
        from streamlit.runtime.scriptrunner.script_runner import RerunException

        raise RerunException()
    except Exception:
        st.session_state._needs_refresh = True
        st.warning("Please refresh the page to see changes.")
        return

# ─────────────────────────────────────────────
# Session state bootstrap
# ─────────────────────────────────────────────

# In-memory registry (no disk). Survives page refreshes while the
# Streamlit server process runs. Lost on server restart.
@st.cache_resource
def owner_registry():
    return {}

registry = owner_registry()


@st.cache_resource
def provider_registry():
    return {}

providers = provider_registry()



vectorstore = init_vectorstore()

# Role selector (no authentication for demo)
role = st.sidebar.selectbox("Role", ["Owner", "Care Provider"])

# Fixed keys for demo sessions (no auth)
OWNER_KEY = "owner1"
PROVIDER_KEY = "provider1"

if "owner" not in st.session_state:
    schedule = WeeklySchedule()
    for day in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday"):
        slot = TimeSlot(
            start=datetime.combine(date.today(), time(7, 0)),
            end=datetime.combine(date.today(), time(21, 0)),
        )
        schedule.add_slot(day, slot)

    # Try to load a previously saved owner from in-memory registry
    loaded = registry.get(OWNER_KEY)
    if loaded:
        st.session_state.owner = loaded
        # restore an active plan reference (use first plan if present)
        if loaded.care_plans:
            st.session_state.plan = loaded.care_plans[0]
        else:
            plan = CarePlan(plan_id="plan-001", plan_date=date.today())
            st.session_state.owner.add_care_plan(plan)
            st.session_state.plan = plan
        st.session_state.task_counter = getattr(st.session_state, "task_counter", 0)
    else:
        # create a fresh owner and save it
        st.session_state.owner = PetOwner(
            username=OWNER_KEY,
            password="",
            name="Your Name",
            availability=schedule,
        )
        plan = CarePlan(plan_id="plan-001", plan_date=date.today())
        st.session_state.owner.add_care_plan(plan)
        st.session_state.plan = plan
        st.session_state.task_counter = 0
        registry[OWNER_KEY] = st.session_state.owner

# Sync session owner from registry so updates made by providers are reflected
reg_owner = registry.get(OWNER_KEY)
if reg_owner:
    st.session_state.owner = reg_owner
    # ensure we have an active plan reference
    if reg_owner.care_plans:
        st.session_state.plan = reg_owner.care_plans[0]

# Initialize a simple provider session object so UI can reference it
if "provider" not in st.session_state:
    loaded_p = providers.get(PROVIDER_KEY)
    if loaded_p:
        st.session_state.provider = loaded_p
    else:
        default_provider = CareProvider(
            username=PROVIDER_KEY,
            password="",
            display_name="Your Clinic",
        )
        st.session_state.provider = default_provider
        providers[PROVIDER_KEY] = default_provider

# Sync provider session from registry
reg_provider = providers.get(PROVIDER_KEY)
if reg_provider:
    st.session_state.provider = reg_provider

owner: PetOwner = st.session_state.owner
plan: CarePlan  = st.session_state.plan
provider: CareProvider = st.session_state.provider

def detect_conflicts_lightweight(tasks):
    """
    Detect tasks scheduled at the same time.

    Returns:
        List[str]: warning messages
    """
    warnings = []

    # Sort tasks by time
    sorted_tasks = sorted(tasks, key=lambda t: t.scheduled_time)

    for i in range(len(sorted_tasks) - 1):
        t1 = sorted_tasks[i]
        t2 = sorted_tasks[i + 1]

        if t1.scheduled_time == t2.scheduled_time:
            msg = (
                f"⚠️ Conflict: {t1.task_type.value} and "
                f"{t2.task_type.value} both at "
                f"{t1.scheduled_time.strftime('%I:%M %p')}"
            )

            warnings.append(msg)

            # mark BOTH as conflicted
            t1.conflicted = True
            t2.conflicted = True

    return warnings

# Handlers for UI actions
def handle_add_pet(owner: PetOwner, name: str, species: str, cat: str, age: int, status: str):
    new_pet = Pet(
        name=name,
        species=species,
        species_category=SpeciesCategory(cat),
        age=age,
        adoption_status=AdoptionStatus(status),
    )
    owner.add_pet(new_pet)
    registry[owner.username] = owner
    st.sidebar.success(f"{name} added!")


def handle_add_task(owner: PetOwner, plan: CarePlan, task_type_val: str, task_time_val, pet_likes_val: bool, notes_val: str):
    proposed_time = datetime.combine(date.today(), task_time_val)

    # CHECK 1: Overlap with existing tasks in the current plan
    for existing_task in plan.tasks:
        if existing_task.scheduled_time == proposed_time:
            st.error(f"🚫 Cannot add task: '{existing_task.task_type.value}' is already scheduled at {task_time_val.strftime('%I:%M %p')}.")
            return # Exit early

    # Create temporary task to check availability
    st.session_state.task_counter += 1
    new_task = Task(
        task_id=f"t{st.session_state.task_counter}",
        task_type=TaskType(task_type_val),
        scheduled_time=proposed_time,
        pet_likes=pet_likes_val,
        notes=notes_val,
    )

    # CHECK 2: Owner availability (uses your backend logic)
    if new_task.check_conflict(owner):
        st.error(f"🚫 Cannot add task: Owner is unavailable at {task_time_val.strftime('%I:%M %p')} according to their schedule.")
        # Reset counter since we didn't use the ID
        st.session_state.task_counter -= 1 
        return # Exit early

    # If both checks pass, add to the system
    owner.add_task(plan.plan_id, new_task)
    registry[owner.username] = owner
    st.success(f"Task '{task_type_val}' added successfully.")
    # No rerun needed here if you want to see the success message, 
    # but usually safe_rerun() is good to refresh the list.

def provider_add_task_to_owner(provider: CareProvider, owner_username: str, plan_id: str,
                               task_type_val: str, task_time_val, pet_likes_val: bool, notes_val: str):
    target_owner = registry.get(owner_username)
    if not target_owner:
        st.error("Target owner not found.")
        return

    proposed_time = datetime.combine(date.today(), task_time_val)

    # 1. Find the specific plan
    target_plan = next((p for p in target_owner.care_plans if p.plan_id == plan_id), None)
    
    # 2. Check for time overlaps in that plan
    if target_plan:
        for t in target_plan.tasks:
            if t.scheduled_time == proposed_time:
                st.error(f"🚫 Conflict: A task already exists at {task_time_val.strftime('%I:%M %p')}. Task rejected.")
                return

    # 3. Create task and check Owner availability
    new_task = Task(
        task_id=f"prov_{provider.username}_{len(target_owner.care_plans)+1}",
        task_type=TaskType(task_type_val),
        scheduled_time=proposed_time,
        pet_likes=pet_likes_val,
        notes=f"(Added by {provider.display_name}) {notes_val}",
    )

    if new_task.check_conflict(target_owner):
        st.error("🚫 Conflict: Owner schedule does not allow for a task at this time.")
        return

    # 4. Success: Commit to registry
    target_owner.add_task(plan_id, new_task)
    registry[target_owner.username] = target_owner
    providers[provider.username] = provider
    st.session_state.provider = provider
    st.success("Task added to owner's plan.")
    safe_rerun()


def provider_claim_patient(provider: CareProvider, owner_username: str, pet_name: str):
    owner_obj = registry.get(owner_username)
    if not owner_obj:
        st.error("Owner not found.")
        return
    pet = owner_obj._get_pet(pet_name)
    if not pet:
        st.error("Pet not found on owner.")
        return
    provider.add_patient(pet)
    # persist changes
    providers[provider.username] = provider
    st.session_state.provider = provider
    registry[owner_obj.username] = owner_obj
    st.success(f"Provider now cares for {pet.name} (owner: {owner_obj.name}).")
    safe_rerun()


def provider_add_task_to_pet(provider: CareProvider, pet: Pet, plan_id: str,
                            task_type_val: str, task_time_val, pet_likes_val: bool, notes_val: str):
    # ensure provider is assigned to this pet
    if pet not in provider.patients:
        st.error("You are not assigned to this pet.")
        return
    owner_obj = pet.owner
    if not owner_obj:
        st.error("Pet has no owner recorded.")
        return
    provider_add_task_to_owner(provider, owner_obj.username, plan_id, task_type_val, task_time_val, pet_likes_val, notes_val)
    # ensure owner registry kept up to date and provider persisted
    registry[owner_obj.username] = owner_obj
    providers[provider.username] = provider
    st.session_state.provider = provider
    safe_rerun()


def provider_add_med_to_pet(provider: CareProvider, pet: Pet, med_name: str, dosage: str, frequency: str):
    if pet not in provider.patients:
        st.error("You are not assigned to this pet.")
        return
    med = Medication(name=med_name, dosage=dosage, frequency=frequency,
                     start_date=date.today(), end_date=date.today()+timedelta(days=30))
    provider.add_medication(pet, med)
    # persist
    registry[pet.owner.username] = pet.owner
    providers[provider.username] = provider
    st.session_state.provider = provider
    st.success(f"Medication '{med_name}' added to {pet.name}.")
    safe_rerun()


def provider_add_medication(provider: CareProvider, owner_username: str, pet_name: str, med_name: str,
                            dosage: str, frequency: str):
    owner_obj = registry.get(owner_username)
    if not owner_obj:
        st.error("Target owner not found.")
        return
    pet = owner_obj._get_pet(pet_name)
    if not pet:
        st.error("Pet not found for owner.")
        return
    # create medication with a default start/end for demo
    med = Medication(name=med_name, dosage=dosage, frequency=frequency,
                     start_date=date.today(), end_date=date.today()+timedelta(days=30))
    provider.add_medication(pet, med)
    registry[owner_obj.username] = owner_obj
    providers[provider.username] = provider
    st.session_state.provider = provider
    st.success(f"Medication '{med_name}' added to {pet.name} by provider.")
    safe_rerun()

# ─────────────────────────────────────────────
# Sidebar — Add a Pet
# ─────────────────────────────────────────────

st.sidebar.title("PawPal+")
st.sidebar.header("Add a Pet")
# Owner profile: name and allergies
st.sidebar.markdown("---")
owner_name_in = st.sidebar.text_input("Owner name", value=st.session_state.owner.name)
if owner_name_in != st.session_state.owner.name:
    st.session_state.owner.name = owner_name_in
    registry[st.session_state.owner.username] = st.session_state.owner

st.sidebar.subheader("Allergies")
with st.sidebar.form("add_allergy_form"):
    new_allergy = st.text_input("Add allergy (free text)")
    add_allergy_btn = st.form_submit_button("Add Allergy")
if add_allergy_btn and new_allergy:
    if new_allergy not in st.session_state.owner.pet_allergies:
        st.session_state.owner.add_allergy(new_allergy)
        registry[st.session_state.owner.username] = st.session_state.owner
        st.sidebar.success("Allergy added")

if st.session_state.owner.pet_allergies:
    for a in st.session_state.owner.pet_allergies:
        cols = st.sidebar.columns([4,1])
        cols[0].write(a)
        if cols[1].button("Remove", key=f"rm_alg_{a}"):
            st.session_state.owner.remove_allergy(a)
            registry[st.session_state.owner.username] = st.session_state.owner
            safe_rerun()

with st.sidebar.form("add_pet_form"):
    pet_name    = st.text_input("Pet name")
    pet_species = st.text_input("Species (e.g. Cat, Dog)")
    pet_cat     = st.selectbox("Category", [s.value for s in SpeciesCategory])
    pet_age     = st.number_input("Age", min_value=0, max_value=50, value=1)
    pet_status  = st.selectbox("Adoption status", [s.value for s in AdoptionStatus])
    add_pet_btn = st.form_submit_button("Add Pet")

if add_pet_btn and pet_name:
    handle_add_pet(owner, pet_name, pet_species, pet_cat, pet_age, pet_status)

def owner_add_appointment(owner: PetOwner, pet_name: str, appointment: Appointment):
    owner.add_appointment(pet_name, appointment)
    registry[owner.username] = owner
    st.success("Appointment added.")

# ─────────────────────────────────────────────
# Main — Owner summary
# ─────────────────────────────────────────────

st.title("🐾 PawPal+ — Today's Schedule")
st.caption(f"📅 {date.today().strftime('%A, %B %d %Y')}")

# Owner: show recommended plans inbox
if role == "Owner":
    st.header("Recommended Plans Inbox")
    if owner.recommended_plans:
        for rp in owner.recommended_plans:
            st.subheader(f"Plan {rp.plan_id} — {rp.plan_date}")
            st.write(f"Created by: {rp.created_by.display_name}")
            if rp.tasks:
                st.write("Tasks:")
                for t in rp.tasks:
                    line = f"- {t.task_type.value} at {t.scheduled_time.strftime('%I:%M %p')}"
                    if getattr(t, 'notes', None):
                        line += f" — notes: {t.notes}"
                    st.write(line)
            if st.button("Apply plan to my care plans", key=f"apply_{rp.plan_id}"):
                # convert RecommendedPlan to CarePlan and add
                new_cp = CarePlan(plan_id=rp.plan_id, plan_date=rp.plan_date, tasks=rp.tasks.copy())
                owner.add_care_plan(new_cp)
                # set newly applied plan as active
                st.session_state.plan = new_cp
                owner.recommended_plans = [p for p in owner.recommended_plans if p.plan_id != rp.plan_id]
                registry[owner.username] = owner
                st.success("Recommended plan applied to your care plans.")
                safe_rerun()
    else:
        st.info("No recommended plans yet.")

    # Owner: show pet medications (read from registry to reflect provider updates)
    st.header("Pet Medications")
    owner_obj = registry.get(owner.username, owner)
    for p in owner_obj.pets:
        st.subheader(f"{p.name}")
        meds = p.medications
        if not meds:
            st.write("No medications recorded.")
        else:
            for m in meds:
                st.write(f"- {m.name}: {m.dosage}, {m.frequency} ({m.start_date.isoformat()} → {m.end_date.isoformat()})")

    # Owner: upcoming appointments
    st.header("Upcoming Appointments")
    for p in owner.pets:
        st.subheader(p.name)
        appts = sorted([a for a in p.appointments if a.date_time.date() >= date.today() and a.status != AppointmentStatus.COMPLETED], key=lambda a: a.date_time)
        if not appts:
            st.write("No upcoming appointments.")
        else:
            for a in appts:
                st.write(f"- {a.date_time.strftime('%Y-%m-%d %I:%M %p')} @ {a.location} ({a.appointment_type.value})")
                if a.notes:
                    st.write(f"  notes: {a.notes}")
                cols = st.columns([1,1])
                if cols[0].button("Cancel", key=f"cancel_{p.name}_{a.appointment_id}"):
                    p.remove_appointment(a.appointment_id)
                    registry[owner.username] = owner
                    st.warning("Appointment cancelled.")
                    safe_rerun()
                if cols[1].button("Modify (+1 day, demo)", key=f"mod_{p.name}_{a.appointment_id}"):
                    a.date_time = a.date_time + timedelta(days=1)
                    registry[owner.username] = owner
                    st.success("Appointment shifted by +1 day (demo modify).")
                    safe_rerun()

    # Owner: add an appointment (next provider visit)
    st.header("Schedule a Visit / Appointment")
    pet_choices = [p.name for p in owner.pets]
    if pet_choices:
        with st.form("owner_add_appointment_form"):
            sel_pet = st.selectbox("Pet", pet_choices)
            appt_date = st.date_input("Date", value=date.today())
            appt_time = st.time_input("Time", value=time(10, 0))
            appt_loc = st.text_input("Location", value="Clinic")
            appt_type = st.selectbox("Type", [a.value for a in AppointmentType])
            appt_notes = st.text_input("Notes (optional)")
            add_appt = st.form_submit_button("Add Appointment")
        if add_appt:
            appt = Appointment(appointment_id=f"a{len(owner.pets[0].appointments)+1}",
                               date_time=datetime.combine(appt_date, appt_time),
                               location=appt_loc,
                               appointment_type=AppointmentType(appt_type),
                               notes=appt_notes,
                               status=AppointmentStatus.SCHEDULED)
            owner_add_appointment(owner, sel_pet, appt)
            safe_rerun()
    else:
        st.info("Add a pet first to schedule visits.")


# If the user selected care provider role, show provider console
if role == "Care Provider":
    st.header("Care Provider Console")
    st.caption(f"👩‍⚕️ Provider: {provider.display_name} ({provider.username})")

    # Provider should only act on their assigned patients
    patients = provider.patients
    # Provider: upcoming scheduled appointments for provider's patients
    st.subheader("Upcoming Appointments For My Patients")
    any_sched = False
    for pet in patients:
        pet_appts = [a for a in pet.appointments if a.status == AppointmentStatus.SCHEDULED and a.date_time.date() >= date.today()]
        if pet_appts:
            any_sched = True
            st.markdown(f"**{pet.name}** (owner: {pet.owner.name if pet.owner else 'unknown'})")
            for a in sorted(pet_appts, key=lambda x: x.date_time):
                st.write(f"- {a.date_time.strftime('%Y-%m-%d %I:%M %p')} @ {a.location} ({a.appointment_type.value}) — by {a.provider.display_name if a.provider else 'N/A'}")
                if a.notes:
                    st.write(f"  notes: {a.notes}")
                c1, c2 = st.columns([1,1])
                if c1.button("Cancel", key=f"prov_cancel_{pet.name}_{a.appointment_id}"):
                    pet.remove_appointment(a.appointment_id)
                    registry[pet.owner.username] = pet.owner
                    providers[provider.username] = provider
                    st.warning("Appointment cancelled.")
                    safe_rerun()
                if c2.button("Complete", key=f"prov_complete_{pet.name}_{a.appointment_id}"):
                    a.complete()
                    registry[pet.owner.username] = pet.owner
                    providers[provider.username] = provider
                    st.success("Appointment marked completed.")
                    safe_rerun()
    if not any_sched:
        st.write("No scheduled appointments for your patients.")
    if not patients:
        st.info("You have no assigned patients. Claim one below.")
        owner_usernames = list(registry.keys())
        if owner_usernames:
            sel_owner = st.selectbox("Select owner to claim from", owner_usernames)
            owner_obj = registry.get(sel_owner)
            pet_choices = [p.name for p in owner_obj.pets]
            if pet_choices:
                sel_pet_name = st.selectbox("Select pet to claim", pet_choices)
                if st.button("Claim patient"):
                    provider_claim_patient(provider, sel_owner, sel_pet_name)
            else:
                st.info("Selected owner has no pets.")
        else:
            st.info("No owners registered yet — ask an owner to sign up first.")
    else:
        # show provider's patients
        pet_labels = [f"{p.name} (owner: {p.owner.name if p.owner else 'unknown'})" for p in patients]
        sel_idx = st.selectbox("Select patient", list(range(len(patients))), format_func=lambda i: pet_labels[i])
        sel_pet = patients[sel_idx]

        st.subheader("Selected Pet")
        st.write(f"**{sel_pet.name}** — Owner: {sel_pet.owner.name if sel_pet.owner else sel_pet.owner}")

        st.subheader("Add Task to Pet's Owner Plan")
        with st.form("provider_add_task_form"):
            p_task_type = st.selectbox("Task type", [t.value for t in TaskType])
            p_task_time = st.time_input("Scheduled time", value=time(8, 0))
            p_pet_likes = st.checkbox("Pet likes this task", value=True)
            p_notes = st.text_input("Notes (optional)")
            p_plan_id = st.selectbox("Plan", [p.plan_id for p in sel_pet.owner.care_plans])
            p_add = st.form_submit_button("Add Task as Provider")
        if p_add:
            provider_add_task_to_pet(provider, sel_pet, p_plan_id, p_task_type, p_task_time, p_pet_likes, p_notes)

        st.subheader("Add Medication to Pet")
        with st.form("provider_add_med_form"):
            med_name = st.text_input("Medication name")
            med_dosage = st.text_input("Dosage (e.g. 5 mg)")
            med_freq = st.text_input("Frequency (e.g. once daily)")
            med_add = st.form_submit_button("Add Medication")
        if med_add:
            provider_add_med_to_pet(provider, sel_pet, med_name, med_dosage, med_freq)

        st.subheader("Add Clinic")
        with st.form("provider_add_clinic_form"):
            clinic_id = st.text_input("Clinic ID", value=f"clinic-{len(provider.affiliated_clinics)+1}")
            clinic_name = st.text_input("Clinic name")
            clinic_address = st.text_input("Address")
            clinic_species = st.multiselect("Species treated", [s.value for s in SpeciesCategory])
            add_clinic_btn = st.form_submit_button("Add Clinic")
        if add_clinic_btn:
            # create CareClinic and attach to provider
            clinic = CareClinic(clinic_id=clinic_id or f"clinic-{len(provider.affiliated_clinics)+1}",
                                name=clinic_name or "Unnamed Clinic",
                                address=clinic_address or "",
                                species_treated=[SpeciesCategory(s) for s in clinic_species])
            provider.add_clinic(clinic)
            st.success(f"Clinic '{clinic.name}' added to provider.")

        # Provider: propose an appointment for the selected pet
        st.subheader("Propose Appointment")
        with st.form("provider_propose_appt_form"):
            pa_date = st.date_input("Date", value=date.today())
            pa_time = st.time_input("Time", value=time(10, 0))
            pa_loc = st.text_input("Location", value="Clinic")
            pa_type = st.selectbox("Type", [a.value for a in AppointmentType])
            pa_notes = st.text_input("Notes (optional)")
            propose_appt = st.form_submit_button("Propose Appointment")
        if propose_appt:
            appt = Appointment(appointment_id=f"prov_a{len(sel_pet.appointments)+1}", date_time=datetime.combine(pa_date, pa_time), location=pa_loc, appointment_type=AppointmentType(pa_type), notes=pa_notes)
            ok = provider.add_appointment(sel_pet, appt, sel_pet.owner)
            # persist
            registry[sel_pet.owner.username] = sel_pet.owner
            providers[provider.username] = provider
            if not ok or appt.status == AppointmentStatus.CANCELLED:
                st.warning("Appointment could not be scheduled (conflict within 3 days).")
            else:
                st.success("Appointment proposed to owner.")
            safe_rerun()

        if provider.affiliated_clinics:
            st.markdown("**Affiliated clinics:**")
            for c in provider.affiliated_clinics:
                cats = ", ".join([cat.value for cat in c.species_treated])
                st.write(f"- {c.name} ({c.clinic_id}) — {cats}")

        # Provider: create and send a recommended plan (multi-task draft)
        st.subheader("Create Recommended Plan Draft")

        # Initialize draft storage
        if "rp_draft_tasks" not in st.session_state:
            st.session_state.rp_draft_tasks = []

        # Add a task to the draft
        with st.form("rp_add_task_form"):
            draft_task_type = st.selectbox("Task type", [t.value for t in TaskType])
            draft_task_time = st.time_input("Time", value=time(8, 0))
            draft_task_pet_likes = st.checkbox("Pet likes this task", value=True)
            draft_task_notes = st.text_input("Notes (optional)")
            add_draft_task = st.form_submit_button("Add task to draft")
        if add_draft_task:
            st.session_state.rp_draft_tasks.append({
                "task_type": draft_task_type,
                "time": draft_task_time,
                "pet_likes": draft_task_pet_likes,
                "notes": draft_task_notes,
            })
            providers[provider.username] = provider
            registry[sel_pet.owner.username] = sel_pet.owner
            st.success("Task added to draft")
            safe_rerun()

        # Show current draft tasks with remove buttons
        if st.session_state.rp_draft_tasks:
            st.markdown("**Draft tasks:**")
            for i, dt in enumerate(list(st.session_state.rp_draft_tasks)):
                cols = st.columns([6, 1])
                cols[0].write(f"{dt['task_type']} at {dt['time'].strftime('%I:%M %p')} — notes: {dt.get('notes','')}")
                if cols[1].button("Remove", key=f"rm_rp_{i}"):
                    st.session_state.rp_draft_tasks.pop(i)
                    registry[sel_pet.owner.username] = sel_pet.owner
                    providers[provider.username] = provider
                    safe_rerun()

        # Create and send the recommended plan (includes all draft tasks)
        with st.form("provider_create_plan_form"):
            plan_id_in = st.text_input("Plan ID", value=f"rp-{sel_pet.name}-{date.today().isoformat()}")
            plan_date_in = st.date_input("Plan date", value=date.today())
            create_plan = st.form_submit_button("Create Recommended Plan")
        if create_plan:
            plan = provider.create_recommended_plan(plan_id=plan_id_in, plan_date=plan_date_in, pet=sel_pet, owner=sel_pet.owner)
            # add all draft tasks
            for idx, dt in enumerate(list(st.session_state.rp_draft_tasks)):
                try:
                    t = Task(task_id=f"rp_task_{idx+1}", task_type=TaskType(dt["task_type"]), scheduled_time=datetime.combine(plan_date_in, dt["time"]), pet_likes=dt.get("pet_likes", True), notes=dt.get("notes", ""))
                    plan.add_task(t)
                except Exception:
                    # skip invalid entries
                    continue
            # persist and clear draft
            registry[sel_pet.owner.username] = sel_pet.owner
            providers[provider.username] = provider
            st.session_state.rp_draft_tasks = []
            st.success("Recommended plan created and sent to owner inbox.")
            safe_rerun()

    st.divider()

    # Hide owner-facing schedule when in provider mode
    st.stop()

pet_names = [p.name for p in owner.pets]
if pet_names:
    st.info(f"**Pets registered:** {', '.join(pet_names)}")
else:
    st.warning("No pets yet — add one in the sidebar.")

# ─────────────────────────────────────────────
# Add a Task
# ─────────────────────────────────────────────

st.header("Add a Task")

with st.form("add_task_form"):
    col1, col2 = st.columns(2)
    with col1:
        task_type  = st.selectbox("Task type", [t.value for t in TaskType])
        task_time  = st.time_input("Scheduled time", value=time(8, 0))
    with col2:
        pet_likes  = st.checkbox("Pet likes this task", value=True)
        task_notes = st.text_input("Notes (optional)")
    add_task_btn = st.form_submit_button("Add Task")

if add_task_btn:
    handle_add_task(owner, plan, task_type, task_time, pet_likes, task_notes)

# ─────────────────────────────────────────────
# Today's Schedule
# ─────────────────────────────────────────────

st.header("Today's Schedule")

TASK_ICONS = {
    TaskType.FEEDING:    "🍽",
    TaskType.WALK:       "🦮",
    TaskType.SHOWER:     "🚿",
    TaskType.MEDICATION: "💊",
    TaskType.GROOMING:   "✂️",
    TaskType.PLAY:       "🎾",
    TaskType.OTHER:      "📌",
}

# Sort tasks chronologically using the same key as the Scheduler
sorted_tasks = sorted(plan.tasks, key=lambda t: t.scheduled_time)

if not sorted_tasks:
    st.info("No tasks yet — add one above.")
else:
    # ── 1. Refresh owner-availability conflict flags ───────────────────────
    for task in sorted_tasks:
        task.check_conflict(owner)

    # ── 2. Detect same-time duplicate conflicts ────────────────────────────
    conflict_warnings = detect_conflicts_lightweight(sorted_tasks)
    if conflict_warnings:
        for msg in conflict_warnings:
            st.warning(msg)
    else:
        st.success("No scheduling conflicts detected.")

    # ── 3. Summary table ──────────────────────────────────────────────────
    import pandas as pd
    table_rows = []
    for task in sorted_tasks:
        icon = TASK_ICONS.get(task.task_type, "📌")
        status = "✅ Done" if task.completed else ("⚠️ Conflict" if task.conflicted else "🕐 Pending")
        table_rows.append({
            "Time": task.scheduled_time.strftime("%I:%M %p"),
            "Task": f"{icon} {task.task_type.value.capitalize()}",
            "Pet Likes": "Yes" if task.pet_likes else "No",
            "Status": status,
            "Notes": task.notes or "—",
        })
    st.table(pd.DataFrame(table_rows))

    st.divider()

    # ── 4. Detailed interactive task rows ─────────────────────────────────
    for idx, task in enumerate(sorted_tasks):
        icon  = TASK_ICONS.get(task.task_type, "📌")
        tstr  = task.scheduled_time.strftime("%I:%M %p")
        label = task.task_type.value.capitalize()
        unique_suffix = f"{task.task_id}_{idx}"

        with st.container():
            col1, col2, col3 = st.columns([2, 5, 2])
            with col1:
                st.markdown(f"**{tstr}**")
            with col2:
                st.markdown(f"{icon} **{label}**")
                if task.notes:
                    st.caption(task.notes)
                if not task.pet_likes:
                    st.warning("Pet dislikes this — but it's required.")
                if task.conflicted:
                    st.error("Outside owner availability — needs rescheduling.")
                elif task.completed:
                    st.success("Completed ✓")
            with col3:
                if not task.completed:
                    if st.button("Mark done", key=f"done_{unique_suffix}"):
                        task.mark_complete()
                        registry[owner.username] = owner
                        st.rerun()
                if st.button("Remove", key=f"rm_{unique_suffix}"):
                    owner.remove_task(plan.plan_id, task.task_id)
                    registry[owner.username] = owner
                    st.rerun()
            st.divider()

    # ── 5. Progress summary ───────────────────────────────────────────────
    completed = sum(1 for t in plan.tasks if t.completed)
    conflicts = sum(1 for t in plan.tasks if t.conflicted)
    if completed == len(plan.tasks):
        st.success(f"All {len(plan.tasks)} tasks completed!")
    else:
        st.caption(f"✅ {completed}/{len(plan.tasks)} tasks completed  |  ⚠️ {conflicts} conflict(s)")

st.divider()
st.header("🐾 PawPal AI Assistant")

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

user_input = st.text_input("Ask about vaccines, safety, or pet care:")

col1, col2 = st.columns([1, 1])

with col1:
    ask_btn = st.button("Ask PawPal")

with col2:
    clear_btn = st.button("Clear Chat")

if clear_btn:
    st.session_state.chat_history = []

if ask_btn and user_input:
    with st.spinner("PawPal is thinking..."):
        response = ask_rag(user_input, vectorstore)

    st.session_state.chat_history.append(("You", user_input))
    st.session_state.chat_history.append(("PawPal", response))

# Display chat
for role, msg in st.session_state.chat_history:
    if role == "You":
        st.markdown(f"**🧑 You:** {msg}")
    else:
        st.markdown(f"**🐾 PawPal:** {msg}")