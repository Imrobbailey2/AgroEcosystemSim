# Increment 1: Canvas round-trip checklist

Goal: prove that UF Canvas saves, resumes and scores a large compressed save
from a SCORM 2004 3rd Edition package **before** the game depends on it.

- Package: `agroeco-scorm-roundtrip.zip`. Download it from the latest
  successful **CI** run on `main` or on the PR (artifact *agroeco-scorm-roundtrip*).
  The artifact download is itself a zip, so unzip it once to get
  `agroeco-scorm-roundtrip.zip`. **Do not unzip that inner file.**
- Time needed: about 20 minutes.
- Use a **real test-student account** if possible. Canvas *Student View* may not
  keep SCORM progress the way a real student does; if you must use it, note
  that in the results.

## Setup (instructor)

1. In the course, open **SCORM** in Course Navigation, then **Upload**.
2. Choose `agroeco-scorm-roundtrip.zip`.
3. Import type: **Graded assignment**. This cannot be changed later.
4. Open the new assignment, keep **100 points**, and **publish** it.
5. Optional: tick *Load this tool in a new tab* and note which setting you used.

## Test (student)

| # | Step | Expected | Result (pass/fail + notes) |
|---|------|----------|----------------------------|
| 1 | Launch the assignment. | *Mode* shows **LMS (API_1484_11 found)**. *Entry* is `ab-initio`. | |
| 2 | Click **Save about 30,000 characters**. | Green result: *Saved 30009 characters…*. Write down the first 12 characters of the sha256: ________ | |
| 3 | Click **Exit session (suspend)**, then close the window or tab. | Result says *Session ended*. | |
| 4 | Relaunch the assignment. | *Entry* is `resume`. Result shows **MATCH: 30009 of 30009 characters**, the same sha256 start as step 2, and *decodes OK*. | |
| 5 | Click **Save about 60,000 characters (stress)**, then **Exit session**, close, and relaunch. | Result shows **MATCH: 60001 of 60001 characters**. A MISMATCH here is not a blocker (see the decision rules). | |
| 6 | Click **Report score 87 out of 100**, then **Exit session** and close. | Result: *Score sent: scaled 0.87…*. | |
| 7 | (Instructor) Open the **Gradebook**. | The student shows **87** (out of 100) for the assignment. Note how long it took to appear. | |
| 8 | Relaunch as the student. Click **Write 3 interaction records**, then **Exit session**. | Result: *Interaction records written: 3*. | |
| 9 | (Instructor) Look for SCORM reports in the SCORM tool or assignment (attempt or interaction details). | Record whether the 3 records (corn yield, net income, N leached) are visible and where. | |
| 10 | Relaunch once more. | Still **MATCH** and *Stored score (scaled)* shows `0.87`. | |

If any step fails, expand the **Log** on the page, copy all of it, and paste it
into the results (it lists every SCORM call and any error code).

## Decision rules

- **Steps 2–4 and 7 pass:** Increment 1 passes. Saving and scoring through Canvas works.
- **Step 5 fails but 2–4 pass:** Increment 1 passes, but Increment 8 sets the save
  budget at the largest size that passed, not 64,000.
- **Step 4 fails (MISMATCH, empty data, or `ab-initio`):** stop. Saving needs a
  redesign (for example, a server-side store or a mandatory downloadable save file)
  before Increment 3 builds on it.
- **Step 7 fails:** stop and check the assignment settings (graded, points,
  published) before redesigning scoring.
- **Step 9:** for information only. It decides how much detail instructors see.

## Results

- Date tested:
- Canvas course:
- Account used (test student / Student View):
- Browser and version:
- New tab setting:
- Overall: PASS / PASS with a lower save budget / FAIL
