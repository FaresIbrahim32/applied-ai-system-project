# PawPal+ Project Reflection

## 1. System Design
Three core actions a user must be able to do 
    1. Upload pet prescriptions in file formats (pdf,doc,docx)
    2. Get a recommended plan on a full day of pet care planned out (approximate times of when to do each action)
    3. Add or modify the plan tasks based on sudden changes in schedule

    for this app's backend , we need 2 entities at least , Pet and Pet Owner.

    Pet Owner (User):
        1. User Auth ( username and password)
        2. Number of pets owned ( one user can have many pets) and each pet's name and species
        3. Owner Pet Allergies ( will be in recommended plan on what tasks to do / how to do them)
        4. Availability (fixed schedule every week)
    Pet :
        1. Species (name and catgeory under which they fall) 
        2. Age
        3. Owner_name -> one pet can be owned by only one owner
        4. Adoption status (stray , adopted , from_previous_owner ,etc )
        5. Conditions (any medical history noted obtained from perspcriptions)
        6. Medications (treating any medical conditions)
        7. Upcoming Vet Appointments

    Care Provider: 
        1. User Auth (can log in as care giver and put info about oneslef)
            1.1 name rendered for pet owner on UI
        2. Species treated (equine -> horses , small_pets -> cats and dogs, livestock -> cattle , zoo-> wildlife animals (lions, tigers,etc))
            2.1 One provider can be for multiple species and can treat multiple pets
    Task :
        1. task type ( entered by user) one user can have many tasks
        2. Pet likes or not ( maybe pet doesnt like it but needs to be done (showering))
        3. time ( when it will be done , date and time)
        4. Conflicted or not ( if conflcited wth Owner schedule then reschedule within 3 days if owner still not available , cancel owner's new appointment , pet gets priority)

    Care Clinic: 
        1.Name 
        2.Species treated
            2.1 Care provider can look for and add clinics based on current pet patient
            2.2 some clinics are only for equine , small_pets etc 

    Methods : 

        Pet Owner registers how many pets he/she has . They also disclose any pet allegries they themselves have. They disclose their schedule avaialbility . They can add new pets , remove pets ,,edit pet info ,add appointments , remove appointments , edit appointments , and edit schedule and remove it. They can add/edit/remove condtions and add /edit/remove adoption status . User can search providers for care based on pet species. 

        Care Provider can add/edit/remove pet medications . They can also add appointments but if that appointment is in conflict with Owner appointment within 3 days, cancel it -> Owner gets priority to cancel and resechudle if their new appointments is within 3 days , after that pet gets priority . Provider can add clinic if no clinics avaialbe for current pet patient . Provider can search clinics based on species treated
    
**a. Initial design**

The initial UML design was built around four core entities derived from the system requirements: PetOwner, Pet, CareProvider, and CareClinic. Supporting classes were added to model domain concepts that each entity depends on: Condition, Medication, Appointment, Prescription, WeeklySchedule, CarePlan, and PlanTask. Two enumerations — SpeciesCategory and AdoptionStatus — were introduced to constrain valid values for species groupings and pet adoption states.

Responsibilities assigned to each class:
- **PetOwner**: Handles user authentication, manages their list of pets, stores personal allergy info and weekly availability, and owns the generated care plans.
- **Pet**: Holds all pet-specific data including species, age, adoption status, and links to its conditions, medications, appointments, and prescriptions.
- **Condition**: Represents a medical condition extracted from a parsed prescription document.
- **Medication**: Stores dosage, frequency, and treatment window for a pet's active medications — managed by the CareProvider.
- **Appointment**: Tracks scheduled vet or care visits, with a status field and a reference to the CareProvider. Conflict resolution logic (owner priority within 3 days) is checked against the owner's WeeklySchedule.
- **Prescription**: Represents an uploaded file (PDF, DOC, DOCX) and its parsed text, from which Conditions are extracted.
- **WeeklySchedule**: Stores the owner's fixed weekly time slots and exposes an availability check used during appointment scheduling.
- **CarePlan**: A daily care plan generated for a PetOwner, broken into ordered PlanTask entries with scheduled times.
- **CareProvider**: Handles provider authentication, tracks which species they treat, manages pet medications and appointments, and can search or add clinics.
- **CareClinic**: Stores clinic name, address, and the species categories it serves — used by providers to find appropriate facilities for a given pet.

**b. Design changes**

- Did your design change during implementation?
Yes my uml diagram changed quite a lot
- If yes, describe at least one change and why you made it.
Initially I had planned user auth for both owner and provider in my first uml diagram, however after testing it out I figured it is way too complex to add for the app . I also figured I may use pypdf to let users upload a dummy prescreiption and have medication text extracted , safe to say that was also complex

Also I had task manipulation initially as a method for owner and provider but when I went back to the project guidlines it was clear Task was its own entity . I also added some more objects like Clinic and Allergies
---

## 2. Scheduling Logic and Tradeoffs

**a. Constraints and priorities**

The scheduler considers three constraints when placing a task on the daily plan:

1. **Owner availability** — the most important constraint. Each task's `scheduled_time` is checked against the owner's `WeeklySchedule` (fixed time slots per weekday). If a task falls outside those slots, `check_conflict()` flags it and the task is blocked from being added. This was prioritised first because a care task that the owner cannot physically perform is useless, regardless of how well everything else is planned.

2. **Duplicate-time conflicts** — two tasks cannot occupy the exact same time slot. `detect_conflicts_lightweight()` scans the sorted task list and flags any pair sharing an identical `scheduled_time`. This prevents the schedule from being ambiguous or physically impossible to follow.

3. **Pet preferences** — each task carries a `pet_likes` boolean. Tasks the pet dislikes (e.g. showering) are still allowed but are surfaced with a visible warning in the UI. This is a soft constraint: it informs the owner without blocking the task, because some unpleasant tasks (medication, grooming) are medically necessary.

Owner availability was treated as the hardest constraint because it gates everything else — if the owner is unavailable, no amount of pet preference or time optimisation matters. Duplicate-time conflicts come second because they make the plan logically inconsistent. Pet preferences are last because they are advisory.

**b. Tradeoffs**

The main tradeoff is **blocking vs. warning for pet preferences**. A stricter scheduler might refuse to add a task the pet dislikes unless it is classified as medically required. Instead, the system allows any task regardless of preference and surfaces a `st.warning` banner so the owner can make the final call.

This is reasonable for this scenario because the owner knows their pet best. A disliked task might still be the right choice (a cat that hates baths still needs one). Blocking it outright would make the app feel paternalistic and reduce its utility. The warning approach respects owner judgement while still making the friction visible.

---

## 3. AI Collaboration

**a. How you used AI**

- How did you use AI tools during this project (for example: design brainstorming, debugging, refactoring)?

I used Claude Code and Copoilot to map out the database schema of the entities that I defined initiallly and adjusting the uml diagram based on that . I used Gemini to help me with choosing sorting algorithms and debugging its implementation . Most of the database methods were debugged by Copoilot based on my prompts on how each type of user (owner or provider) should interact with the app and see his/her methods in action. I also used Claude Code to write test cases with Pytest

- What kinds of prompts or questions were most helpful?


**b. Judgment and verification**
- Describe one moment where you did not accept an AI suggestion as-is.

GPT 5 with Copoilot kept ignoring my prompts about owner dashboard and how it should it look (as in an owner should see medication, appointments and other info) and kept and initially suggested appointment scheduling only on Provider's side to which I had to stop it in the midst of its generation and push back on this

- How did you evaluate or verify what the AI suggested?
I kept running the streamlit app and putting dummy info to test the methods I had defined already in my schema

---

## 4. Testing and Verification

**a. What you tested**

Ten tests were written covering three core scheduler behaviors:

- **Task completion** (`test_mark_complete_changes_status`) — verified that calling `mark_complete()` flips the `completed` flag from `False` to `True`. This is the most basic state transition in the system; if it breaks, the entire "mark done" flow breaks with it.

- **Task addition** (`test_adding_task_increases_count`) — confirmed that `PetOwner.add_task()` correctly routes a task into the right `CarePlan` and grows its list. Important because the owner and plan are loosely coupled through an ID lookup, which could silently fail.

- **Sorting correctness** (`test_tasks_sorted_chronologically`, `test_two_tasks_at_same_time_both_present`) — verified that tasks sort into ascending time order regardless of insertion order, and that two tasks at the same time both survive the sort without either being dropped. Sorting is the foundation of a readable daily schedule.

- **Recurrence logic** (`test_daily_recurrence_creates_next_day_task`, `test_weekly_recurrence_creates_next_week_task`, `test_no_recurrence_returns_none`) — confirmed that daily and weekly recurring tasks produce a correctly offset successor on completion, and that tasks with no recurrence attribute return `None`. This matters because `recurrence` is set dynamically rather than declared in the dataclass, making it easy to accidentally omit.

- **Conflict detection** (`test_conflict_flagged_when_owner_has_no_availability`, `test_no_conflict_when_task_falls_within_available_slot`, `test_two_tasks_same_time_both_flagged_when_no_availability`) — verified the full range of the availability check: no slots → always conflicted, task inside a slot → not conflicted, two same-time tasks → both independently flagged. These tests protect the most safety-critical logic in the system.

These tests were important because they exercise the scheduler's three guarantees: a plan is in order, recurring tasks never require manual re-entry, and the owner's time is always respected.

**b. Confidence**

**★★★★☆ (4 / 5)**

Confidence is high for the core scheduling path. All 10 tests pass and cover both happy paths and the main edge cases (empty availability, duplicate times, chain of recurrences). The one area of fragility is the `recurrence` attribute: it is not a declared `dataclass` field, so it must be manually set with `t.recurrence = "daily"`. A contributor who creates a `Task` without knowing this contract will silently get a non-recurring task with no error. Formalising `recurrence` as an optional field with a default of `None` would close that gap and push confidence to 5/5.

Edge cases to test next with more time:
- A recurring task that has already been completed multiple times in a chain (ID collision risk: `t1_next_next_next`).
- `build_medication_schedule()` when the pet has zero active medications on the plan date (empty output, no crash).
- `build_allergy_guidelines()` with an allergy keyword that matches multiple entries in `_ALLERGY_TASK_MAP` simultaneously.
- `get_upcoming_appointments()` when all appointments are cancelled or completed (should return an empty list, not error).

---

## 5. Reflection

**a. What went well**

- What part of this project are you most satisfied with?
 Overall database is a bit more nunaced that just pets and their owners and some scheudler . Maybe I can extend this into a full on react native project beacuase of how much detail I added to the schema

**b. What you would improve**

- If you had another iteration, what would you improve or redesign?
Maybe instead of streamlit , I would choose Vue or any other rich library that would make UX a bit more lively

**c. Key takeaway**

- What is one important thing you learned about designing systems or working with AI on this project?
Always link the markdown file under the agents dir when prompting so that the model knows how it should generate code properly


# ⚖️ Responsible AI Reflection

AI in PawPal+ is designed to be helpful but also transparent about its limits.

## Limitations and biases

* The system only knows what is in the provided documents
* Missing or incomplete document coverage leads to incomplete answers
* It does not account for individual pet conditions (breed, medical history)
* Frequently mentioned topics may be overrepresented

---

## Potential misuse and safeguards

The AI could be misused if treated as a replacement for veterinary advice.

To reduce this risk:

* It recommends consulting a licensed vet
* It only answers using retrieved document context
* It admits when information is not found instead of guessing

---

## Reliability insights

* Performs well when relevant context exists
* Struggles with vague or out-of-scope questions
* Initially produced confident but weak answers; improved after enforcing strict context-only responses

---

## Collaboration with AI

* **Helpful:** Suggested switching to Chroma for persistent embeddings, improving stability
* **Flawed:** Recommended an unsupported embedding model, causing runtime errors and requiring manual fixes

---

## Summary

* Reliable within document scope, but limited beyond it
* Safeguards reduce hallucination and misuse
* AI accelerated development but required validation

