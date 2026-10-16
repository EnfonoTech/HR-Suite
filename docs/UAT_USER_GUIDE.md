# HR Suite GCC module — UAT user guide

What each feature does, how it works, and exactly how to test it. Figures in the examples are the ones the automated tests check, so a wrong number is a real finding.

**Read first:** `docs/GCC_LEAVE_GRATUITY_GUIDE.md` (the model) — this guide is the hands-on version.

---

## 0. Before you test

### 0.1 Who you need
| Role | Used for |
|---|---|
| HR Manager | Everything below; Country Config, settlements, advices |
| HR User | Raise leave/sick, raise payment advices |
| **HR Leave Override** (add this role to one test user) | Advance leave, leave before the waiting period, paying leave salary below the barrier, submitting sick leave without a certificate |
| Two approver users (any user with HR User) | Level 1 and level 2 of the payment advice |
| Accounts User/Manager | Finance side of a payment advice |

### 0.2 Switch the features on (they are OFF on existing Country Configs)
The module never switches an existing site by itself. For testing, turn on what you need:

| Switch | Where | Turn on to test |
|---|---|---|
| Leave Accrual Engine = HR Suite Ledger | Country Config → Annual Leave Policy | §3 Ledger, §4 Settlement |
| Split Sick Leave Into Pay Tiers Automatically | Country Config → Sick Leave Policy | §5 Sick leave |
| Approvers table | Hr Suite Settings → HR Payment Advice Approval | §6 Approval |
| Route Expense Claims Through A Payment Advice | Hr Suite Settings | §6.4 |

Switch on **one test country** (e.g. Saudi Arabia) and test with employees of that country only.

### 0.3 Test employees
Create (or pick) employees with: **Work Country** set (Employee → Leave & End-of-Service Policy section sits under Work Country), a **Date of Joining**, a **Salary Structure Assignment** (or CTC), and a **Holiday List** on the company. Note each employee's monthly salary: examples use **4,000 SAR a month, all one component** (daily 133.33 on a 30-day month).

> **Weekly offs matter.** Leave days are counted by HRMS *after* holidays. If your Holiday List marks Fridays, a 30-day calendar leave counts fewer days. Always read the **Leave Days** field on the Leave Application, not the calendar.

### 0.4 What the monthly job does and how to run it for a test
Accrual runs automatically at 03:00 on the 1st for the month just ended. To test without waiting, ask the Enfono developer to run it, or from a bench console:
```
bench --site <site> execute hr_suite.hr_suite.leave_accrual.run_accrual --kwargs '{"through": "2026-10-31"}'
```
(`through` is any date in the last month to accrue. Safe to repeat.)

---

## 1. Country policy (Country Config)

**What it is.** One Country Config per country holds the legal defaults: annual-leave bands, leave-salary barrier, sick-leave tiers, gratuity slabs and resignation factors. The employee's country (contract → Employee Work Country → Company country) picks the policy.

**Countries:** Saudi Arabia, Bahrain, Oman, UAE, Qatar, Kuwait (India unchanged).

**How to test**
1. Open **Country Config → SA**. Check the sections: *Annual Leave Policy*, *Leave Salary Settlement*, *Sick Leave Policy*, *Gratuity Policy*.
    - Expect annual bands **21 days from 0 months, 30 days from 60 months**; sick tiers **30 @100%, 60 @75%, 30 @0%** (120 days); gratuity slabs **0–5 yrs ½ month, 5+ yrs 1 month**; resignation factors **0% (<2y), 33.33% (2–5y), 66.67% (5–10y), 100% (10y+)**.
    - Also open BH, OM, AE, QA, KW and compare with `GCC_LEAVE_GRATUITY_GUIDE.md`.
2. **Validation:** on a test copy, try (each must be refused with a clear message):
    - two bands starting at the same month;
    - sick tiers that don't add up to *Sick Days / Year*;
    - overlapping gratuity slabs; a percentage of 150.
3. Open an **Employee** → section *Leave & End-of-Service Policy*. The read-only panel must show country, service months, band, leave days/yr, barrier, sick tiers, gratuity.
4. **Override:** on the Employee, set *Leave Days / Year = 30*, *Leave-Salary Days / Year = 21*. The panel shows "Override: leave days per year, salary days per year" and the monthly rates become **2.5 leave days and 1.75 salary days**.

**Pass:** values match the spec; bad values are refused; panel and override work.

---

## 2. Gratuity (End of Service Benefit)

**How it works.** One engine for all countries (India keeps the Gratuity Act). Qualifying service = days from joining to exit (or to the scheme cut-off) **minus unpaid leave and unpaid absence**, ÷ 365. Rate comes from the slabs, resignation factors apply only on resignation, then cap and minimum service.

**How to use.** *End of Service Benefit → New*: pick employee, termination date, termination reason, enter last basic salary. The form calculates live and fills the **Gratuity Breakdown** (calendar days, unpaid days, qualifying days, wage base, per-slab rows). Termination reason **Partial Settlement** pays gratuity accrued to date and does **not** mark the employee Left on submit.

**Test cases (base wage 10,000 unless stated, exits via Termination by Employer unless stated)**

| # | Country | Service | Exit | Expect |
|---|---|---|---|---|
| G1 | KSA | 3 years | Termination | **15,000** (3 × ½ × 10,000) |
| G2 | KSA | 8 years | Termination | **55,000** (25,000 + 30,000) |
| G3 | KSA | 8 years | Resignation | **36,668.50** (66.67%) |
| G4 | KSA | 3 years | Resignation | **4,999.50** (33.33%); under 2 yrs → **0** |
| G5 | KSA | 8 years | Dismissal | **0** |
| G6 | KSA | 3 yrs with 365 days unpaid leave | Termination | **10,000** (2 qualifying years) |
| G7 | UAE (base 6,000) | 6 years | Resignation | **27,000** (21 days ×5, then 30 days; resignation pays in full) |
| G8 | UAE | 0.5 year | Termination | **0** (1 year minimum) |
| G9 | UAE (6,000) | 30 years | Termination | **144,000** (capped at 24 months) |
| G10 | Bahrain (500) | joined 2020-01-01, exit 2026-01-01 | Termination | service counted only to **1 Mar 2024** (employer gratuity cut-off); note on the document says so |
| G11 | Bahrain | joined after 1 Mar 2024 | any | **0** (funded by SIO) |
| G12 | Oman (400) | 5 years | Resignation | **2,000** (flat month a year, resignation in full) |
| G13 | Qatar (5,000) | 2 years | Termination | **7,000** (3 weeks = 0.7 month a year) |
| G14 | Kuwait (400 KWD) | 7 years | Termination / Resignation | **1,800 / 1,200.06** (15 days ×5 + 1 month ×2; 66.67% on resignation) — Kuwait bands carry a VERIFY note |
| G15 | any | exit before joining; deductions larger than payable | | refused with a message |

To get exact years in a test, use joining/exit dates 365 × N days apart (a leap year adds a day).

**Also check:** a Qatar or Kuwait employee no longer produces a Saudi figure; the report **Gratuity Liability** (§7) shows the same numbers; an **Employee Separation** submit still creates a draft End of Service Benefit (and shows a warning if it could not).

---

## 3. Leave Accrual Ledger and the monthly accrual

**How it works.** One ledger row per employee per month: *days worked*, *leave days*, *leave-salary days*. Leave days also top up the employee's HRMS **Annual Leave** allocation, so Leave Applications and payroll keep working. Leave-salary days are a **second balance**, held only in the ledger.

Month rules: a full month earns exactly the monthly rate (2.5 or 1.75) whatever its length. The joining month, exit month, **annual-leave days** and **unpaid days** reduce it; **sick leave does not**. Default part-month method: *days worked ÷ 30* (Country Config → **Part-Month Accrual**; "Month Fraction" is the alternative).

### 3.1 Go-live set-up (do this once per test country)
1. Prepare opening balances CSV from `hr_suite/data/leave_opening_balance_template.csv` (Employee, Source = Opening, Period End = a **month end**, Leave Days, Leave-Salary Days).
2. **Data Import → Leave Accrual Ledger → Insert New Records** → upload.
   Check: ledger rows exist; each employee's **Leave Allocation** now holds the opening leave days.
3. Country Config → **Leave Accrual Engine = HR Suite Ledger**. Leave **Ledger Accrues From** as the first of the month after the opening date.
4. The daily leave-type sync (or ask the developer to run it) turns **off** HRMS earned-leave for Annual Leave and allows a negative balance. Check *Leave Type → Annual Leave*: **Is Earned Leave unticked, Allow Negative Balance ticked.**

**Check before you switch a country on.** Annual leave allocated some other way (an old Leave Policy Assignment, or by hand) sits *under* the ledger, so the balance becomes that allocation **plus** everything accrued. On the Country Config of a ledger country, **Actions → Run Accrual Now** accrues every month still owed (safe to repeat) and lists any allocation the ledger did not make: cancel it, or enter it as the opening balance. The monthly job itself runs at 03:00 on the 1st, so a country switched on mid-month shows nothing until then unless you use this button.

### 3.2 Tests
| # | Do | Expect |
|---|---|---|
| L1 | Employee joined 15 Jan, 21 days/yr (1.75/month). Run the accrual through March | 3 ledger rows. Jan **days worked 17 → leave 0.99**; Feb 30 → **1.75**; Mar **1.75**. HRMS balance = **4.49**. |
| L2 | Run the same accrual again | **No new rows** (idempotent). |
| L3 | Skip a month's run, then run later | The missed months are made up. |
| L4 | Employee with > 5 years' service (KSA) | **2.5 leave days / month** (30-day band). |
| L5 | Override 30 leave / 21 salary days on the employee | Accrual rows show leave **2.5**, salary **1.75**. |
| L6 | Approve 5 days annual leave inside a month, run accrual | That month's *days worked* drops by 5. Sick leave in the month changes nothing. |
| L7 | Joining on 9 March, over-30 method | **23 days worked → 1.92** (at 2.5/month). Switch Part-Month Accrual to *Month Fraction* → **1.85**. |
| L8 | Opening balance 12, accrue through April (opening dated 28 Feb) | Only **March and April** accrue; running balance 12 → 14.5 → 17 (30-day band). |
| L9 | Try a second Opening row for the same employee; try Opening after accrual has run | Both refused. |
| L10 | Add an **Adjustment** (e.g. −0.75 leave, −0.5 salary) | Both balances move; deleting any ledger row is **refused**. |
| L11 | Log in as an ordinary user and apply for **more annual leave than the balance** | Refused: "Only HR can approve annual leave beyond the balance". |
| L12 | Same application as a user with **HR Leave Override** | Allowed; balance goes negative; next accruals bring it back. |
| L13 | Bahrain employee (12-month wait) applies for annual leave at 6 months' service | Refused unless HR Leave Override. |

---

## 4. Leave Salary Settlement

**How it works.** Created from an **approved annual Leave Application** on the last working day. It prices:
- **Worked-days salary** — from the 1st of the month to the last working day, over 30 days, only when Country Config **Pay Worked Days In Settlement** is ticked (default).
- **Leave salary** — (sum of the policy's salary components ÷ 30) × **earned salary days**.
- **Air ticket** (if the employee has the ticket override and it is due), less anything an old Annual Leave Disbursement already paid.

**Minimum service:** leave salary is paid only once the employee has **365 days (12 months) of service from the joining date** — editable per country (*Minimum Service From Joining*). Before that the settlement is **refused with the reason** ("service 334 of the 365 days needed"). Once met, **every day accrued since joining is paid**: the first 12 months' days are not lost. An optional second barrier, *Minimum Earned Leave-Salary Days*, is **0 (off)** by default. Only **HR Leave Override** can tick *Pay Below The Barrier* (with a reason). Only **earned** days are paid; the part not yet earned stays as *Salary Days Still Due* for a later settlement.

**On exit:** create the settlement with **Settlement Type = Final Settlement** and the last working day. It pays the leave days accrued and unused **whatever the service** (Country Config *Pay Accrued Leave On Exit Below Minimum Service*, ticked by default; untick to apply the minimum on exit too). Worked days and gratuity are paid by the Salary Settlement and the gratuity calculation, not here.

**Payroll:** month-end payroll must not pay the same days. Submitting books **Additional Salary deductions** (component *Leave Salary Recovery*), one per month, each capped at one month's pay. HR records no accounting; the settlement goes to a **Payment Advice**.

### 4.1 Worked example (use this)
Salary **4,000/month**, employee with 40 earned salary days and > 1 year service. Leave **11 Nov – 10 Dec 2026** (30 days), last working day **10 Nov**.
1. *Leave Application* (submitted, Approved) → button **Create → Leave Salary Settlement**.
2. Expect on the draft: Worked-days salary **1,333.33** (10 days), Leave salary **4,000.00**, **Total 5,333.33**, barrier met.
3. Submit. Expect:
    - Leave Accrual Ledger: a **Settlement** row **−30 salary days** (balance 40 → 10).
    - **Additional Salary** rows: **4,000 dated 10 Nov** (worked 1,333.33 + 20 leave days) and **1,333.33 dated 1 Dec** (10 leave days).
    - Button **Create → Payment Advice** raises the advice for 5,333.33.
4. Set **Pay Worked Days In Settlement = off** in Country Config and repeat with another employee: total **4,000**; deductions **2,666.67** (Nov) and **1,333.33** (Dec).

### 4.2 Tests
| # | Do | Expect |
|---|---|---|
| S1 | Example above | As stated. |
| S2 | Employee with **11 months'** service (joined 11 May 2025, last working day 10 Apr 2026) | Settlement **refused** at save: "service 334 of the 365 days needed". Nothing is spent from the ledger. |
| S2b | Employee joined 10 Apr 2025 (exactly 12 months), 21 earned days, salary 6,000, 21 days of leave | Allowed. Leave salary **4,200** (6,000 ÷ 30 × 21). Ledger −21. |
| S2c | **Final Settlement** for an employee with 6 months' service and **10.5** earned days, salary 6,000 | Allowed: leave salary **2,100**, no worked days. Untick *Pay Accrued Leave On Exit…* and it is refused. |
| S3 | An employee short of service; ordinary HR user ticks *Pay Below The Barrier* | Refused (needs HR Leave Override). |
| S4 | As HR Leave Override, tick it, **leave the reason blank** | Refused; with a reason: pays what is earned, the rest stays due. |
| S5 | After more days are earned (≥ 30) create a second settlement for the same leave | Pays the remaining days; **no worked days, no ticket, no new payroll deductions**. |
| S6 | Try a second *draft* settlement for the same leave | Refused. |
| S7 | **Cancel** a submitted settlement | Salary days returned (balance back to 40), Additional Salary rows cancelled. |
| S8 | Country not on the Ledger engine | Refused with a message. |
| S9 | Try to create an **Annual Leave Disbursement** for a ledger country | Refused: "Use Leave Salary Settlement". |
| S10 | A month's Salary Slip already submitted, then submit a settlement hitting it | Refused ("Payroll Already Run") — cancel and re-run that slip first. |

### 4.3 Record Rejoin (button **Actions → Record Rejoin**, on the first settlement of a leave)
| # | Rejoin date (leave 11 Nov–10 Dec) | Expect |
|---|---|---|
| R1 | **1 Dec** (early) | Unused **10 days**; **1,333.33 recovered** at payroll on 1 Dec; **10 salary days restored** to the balance; later months freed. Reminder shown to shorten the Leave Application. |
| R2 | Change to **6 Dec** | Previous effects reversed, new ones applied (5 unused days). |
| R3 | **15 Dec** (4 days late), employee has leave balance | 4 days "covered by leave balance" (HR records an extension Leave Application so payroll pays them as leave). |
| R4 | Late return **beyond** the balance | Those days are **unpaid** and deducted at payroll. |

---

## 5. Sick leave in pay tiers

**How it works.** The employee applies for plain **Sick Leave**. The days are laid along the country's tiers starting from what they already used **in the leave year** (KSA: day 31 is the first at 75%). HRMS still pays the leave in full; payroll takes the unpaid share back with a **Sick Leave Deduction** per month. Sick leave never touches the annual balance.

- **Before eligibility** (Bahrain/Qatar 3 months; UAE after probation): days are unpaid and use no tier. **Past the last tier:** unpaid.
- Tiers are used **in date order**: submitting or cancelling a leave re-splits **every sick leave from that date onward** and re-books only what changed. Tiers apply **per day**, so one leave can be part full pay and part 75%.
- **Window:** Country Config → *Sick Leave Pay Window* sets the span in which sick days count: **Leave Period** (default; calendar year if the company has none), **Calendar Year**, **Rolling 12 Months** (looks back 12 months from each leave) or **Service Year** (joining anniversary).
- **A month already paid is never edited.** If a recalculation changes the amount for a month whose Salary Slip is submitted, the difference is booked on the **next open payroll date**: an extra *Sick Leave Deduction* if more is unpaid, or a *Sick Leave Adjustment* earning if less. Open months are simply re-booked.
- **Medical certificate** field: required to submit (HR Leave Override can submit without).

**Tests** (Saudi employee, salary 3,000 → daily 100, sick allocation 120; Holiday List without weekly offs, or use days that skip them)
| # | Do | Expect |
|---|---|---|
| K1 | Draft a **40-day** sick leave | Table shows **30 Full pay + 10 at 75%**, unpaid-equivalent **2.5** — *before* submitting. |
| K2 | Submit it | One **Sick Leave Deduction** of **250** dated the first reduced day. |
| K3 | A second 20-day leave afterwards | **All 20 at 75%** (days 41–60), deduction **500**. |
| K4 | Submit a **later** leave first, then an earlier one | The later one re-splits automatically and its deduction appears. |
| K5 | Cancel the earlier leave | The later one gets its tiers back; the deduction is cancelled. |
| K6 | Bahrain employee joined 1 Feb applies for sick leave 10–14 Feb | All 5 days **Before eligibility** (unpaid), deduction 5 × daily. |
| K7 | Submit with no certificate as an ordinary HR user | Refused; with HR Leave Override allowed. |
| K8 | Annual leave application | **No** sick table, no deduction. |
| K9 | Country with the switch **off** | Nothing is split or deducted (existing sick-leave set-up untouched). |
| K10 | Saudi employee, 100 a day. Submit **20 days** (3–22 Aug), then **10 days** (12–21 Nov, "0010"), then **40 days** (15 Sep–24 Oct, "0008") | 0008: **10 Full + 30 at 75%**, deduction **750**. 0010 first showed **10 Full pay**; after 0008 it shows **10 at 75%** (previous days = 60), deduction **250**. |
| K11 | Repeat K10 with November's Salary Slip already submitted | 0010's November is untouched; an **extra deduction of 250** appears on the next open payroll date. Cancel 0008: a **Sick Leave Adjustment earning of 250** is booked. |
| K12 | Set *Sick Leave Pay Window* = Service Year; employee joined 1 Jul 2025; 30 days in May 2026, 11 days in July 2026 | The July leave is **Full pay** (a new service year starts 1 Jul). With the default window it is 75%. |

The legacy **Sick Leave** document: new ones are refused where the split is on; where it is off it now prices from the country's tiers (KSA 40 days at salary 3,000 → **3,750**) and the yearly limit is the country's, not a fixed 120.

---

## 6. HR Payment Advice (approval)

**How it works.** Every payment to an employee outside payroll passes the HR Payment Advice: lines have **Claimed** and **Sanctioned** amounts (HR can sanction less, never more; Finance pays the sanctioned total). Flow:

`Draft → Pending Approval (Level 1 → Level 2) → Approved → Sent to Finance → Paid` — or **Rejected** back to HR.

Approvers are set per company in **Hr Suite Settings → HR Payment Advice Approval → Approvers** (level 1 required; level 2 optional). With **no approver** for a company, submitting the advice is the approval (old behaviour).

### 6.1 Tests
| # | Do | Expect |
|---|---|---|
| P1 | New advice, two lines 100 and 250, sanction 100 and 200 | Totals: **claimed 350, sanctioned 300**. Sanction 150 on a 100 line → refused. A line at 0 is fine. |
| P2 | With approvers configured, press **Submit** directly | Refused: "use Send for Approval". |
| P3 | **Send for Approval** as HR | Status *Pending Approval*, waiting for level 1; the approver gets a to-do. |
| P4 | Level 1 approver clicks **Approve** | Waits for level 2. |
| P5 | The **same person** tries level 2 | Refused. |
| P6 | Level 2 approver approves | Advice **submits itself**, status **Approved**. |
| P7 | While pending, HR edits a sanctioned amount | Refused (locked); **Recall** returns it to Draft. |
| P8 | Approver clicks **Reject** with no reason / with a reason | Reason required; status **Rejected**, reason + who shown, comment added, claimant mailed; **not** in Finance's queue. |
| P9 | HR corrects and **Send for Approval** again | Goes round again. |
| P10 | After approval: **Send to Finance**, then **Mark as Paid** (reference required) | Status Sent to Finance → Paid; the source document shows Paid. |
| P11 | **Print → HR Payment Approval Sheet** | Header, lines (claimed/sanctioned), totals + words, signature blocks: Claimant, HR, Level 1, Level 2, Finance, with approval dates. |
| P12 | A wrong person clicks Approve | Refused ("waiting for <user>"). |

### 6.2 Where payment advices come from
Buttons on the source documents: Leave Salary Settlement (**Create → Payment Advice**), End of Service Benefit, Leave Encashment, Gratuity, Annual Leave Disbursement, Salary Settlement; or create one by hand (*Payment Type* = Other/Ticket).

> **Note for this site:** if **sf_trading's Payment Advice** is installed, the *Create → Payment Advice* buttons raise **sf_trading's** advice (the Finance queue), not the HR one. The two-level approval described here applies to the **HR Payment Advice**. Expense Claim routing (below) always uses the HR one.

### 6.3 Queue report
**HR Payment Advice Queue** — filter *Stage*: Awaiting Payment / Awaiting Approval / Rejected / All Open.

### 6.4 Expense Claims through the advice
Switch **Route Expense Claims Through A Payment Advice** on (Hr Suite Settings).
| # | Do | Expect |
|---|---|---|
| X1 | Submit an approved Expense Claim (claimed 500, sanctioned 450) | An HR Payment Advice appears: claimed **500**, sanctioned **450**, type *Expense Claim*, approvers filled. |
| X2 | Create a **Payment Entry** against that claim while the advice is Draft/Pending | Refused: "cannot be paid yet … advice is …". |
| X3 | Approve the advice, then create and submit the Payment Entry | Allowed; the advice turns **Paid** with the Payment Entry as reference. Cancel the Payment Entry → advice goes back to *Sent to Finance*. |
| X4 | Cancel the Expense Claim | Its unpaid advice is withdrawn; a **paid** advice blocks the cancel. |
| X5 | A claim submitted **before** routing was switched on | Not affected. |

## 6A. Annual leave: minimum service, linked leave types, approval, currency

### 6A.1 Annual leave before the minimum service
Country Config → *Annual Leave Before Minimum Service*:
- **Allow** (default): leave may be taken; no leave salary is paid until the minimum service is met.
- **Block:** a Leave Application for annual leave starting before the minimum service is **refused**.
- **Unpaid:** the application goes through and payroll **deducts those days** (Additional Salary, component *Leave Before Minimum Service Deduction*, one per month).

### 6A.2 "Can Be Taken From Leave" (Leave Policy)
On a **Leave Policy** row, the column **Can Be Taken From Leave** names the leave type whose balance this type uses. Example: *Emergency Leave* → *Annual Leave*.
| # | Do | Expect |
|---|---|---|
| L1 | Open a Leave Policy | The column is in the grid. |
| L2 | Policy row: Emergency Leave, 5 days, **Can Be Taken From = Annual Leave**; save | Message that Emergency Leave now allows a negative balance of its own. A type cannot name itself. |
| L3 | Employee with 7 days of Annual Leave applies for **2 days of Emergency Leave**; approve | **Annual Leave balance 5**; Emergency Leave balance unchanged. |
| L4 | Apply for more days than Annual Leave holds | Refused ("…is taken from Annual Leave, which has 5 day(s) left"). Annual leave on the ledger engine may go negative only for **HR Leave Override**. |
| L5 | Cancel the leave | The days return to Annual Leave. |

### 6A.3 Leave approval (Approve / Reject)
A workflow **Leave Application Approval** is installed on the Leave Application (inactive if the site already runs another active workflow on it — the log says so). States **Open → Approved / Rejected**.
| # | Do | Expect |
|---|---|---|
| W1 | Employee (with a user) applies, naming a **Leave Approver** | Status **Open**. |
| W2 | The named approver opens it | Buttons **Approve** and **Reject** (also in the Workflow Action list). Another Leave Approver sees none. |
| W3 | Approve | Submitted, **Approved**, balance reduced. |
| W4 | Reject another | Submitted, **Rejected**, balance **unchanged**. |
| W5 | The employee (even with HR Manager) opens their own leave | **No** approve / reject buttons: nobody approves their own leave. |
| W6 | If buttons are missing on a site | Run `bench --site SITE execute hr_suite.hr_suite.leave_workflow.diagnose --kwargs "{'application': 'HR-LAP-…', 'user': 'approver@…'}"`: it lists the cause (no active workflow, role missing, condition false, permission, self-approval). |
**Do not set Status to Approved by hand.** That leaves the leave *not submitted*: no Submit button, no balance deduction, and it is missing from the Leave Salary Settlement list and from the sick-pay tiers. The system now refuses it; always use the **Approval** menu. HR may create a leave for an employee and approve it as the named approver or HR Manager; only an employee approving their *own* leave is blocked. A leave left stuck by hand is put back to *Open* on deployment.

No alert e-mail is sent by this workflow on purpose (a PDF failure would undo the approval); approvers use the Workflow Action list and HRMS leave notifications.

### 6A.4 Payment Advice approval, automatic
- **Approvers are set per company** in *Hr Suite Settings → HR Payment Advice Approval* (level 1, optionally level 2). A company with **none** keeps the old behaviour, where submitting the advice is the approval, and *Send for Approval* answers "No Approver". Add the approvers first.
- With approvers set, a bare **Submit is refused** ("Approval Required"); the last approver's *Approve* submits it.
- **A submitted Leave Salary Settlement now raises its Payment Advice by itself** (within seconds, in the background) and, where approvers are set, sends it for approval, so level 1 is assigned with no clicks. If anything stops it, the **Create → Payment Advice** button still works and the Error Log says why.

### 6A.5 Saudi Arabia gratuity in the standard Gratuity form
The HRMS **Gratuity Rule** list now contains **Saudi Arabia - Termination / End Of Contract** (also Oman and Qatar), built from the Country Config slabs: 15 days a year for 5 years, then 30, with part years pro-rated (7 years on 6,000 = 27,000). **Resignation** reductions, caps and the Bahrain scheme cannot be written as HRMS rules, so those cases are calculated in HR Suite (Gratuity Liability report, end-of-service benefit), not in the standard Gratuity form.

### 6A.6 Salary Structure currency
A new **Salary Structure** takes the **company's default currency** (SAR for a Saudi company, BHD for a Bahrain one) when the company is chosen, whatever the user's own default is. Choosing another currency shows a warning. To find structures already in the wrong currency: `bench --site SITE execute hr_suite.hr_suite.salary_currency.mismatches`; draft ones can be edited, submitted ones are replaced by amending or creating a new structure and assignment.

---

## 7. Reports (HR Suite workspace → Employee & Leave Reports)

| Report | Check |
|---|---|
| **Leave and Salary Days Balance** | One row per employee: country, engine, band, leave days/yr, salary days/yr, **leave balance**, salary days earned / settled / balance, "Leave Salary Payable" Yes/No with the shortfall. Filter *Ledger Engine Only*. Non-ledger employees show no salary-day figures. |
| **Leave Accrual Ledger Report** | One row per transaction: date, employee, leave type, **transaction** (Opening, Accrual, Adjustment, Settlement, **Leave Taken**, Leave Encashment), **days in / days out**, **running** leave and salary balance, and a **link to the source document**. The leave running balance agrees with the Leave Balance Report. Filter by source and period. |
| **Leave Balance Report** | **Annual Entitlement**, **Accrued To Date**, **Accruing This Month** (earned so far, credited at month end) and **Balance** (accrued − taken). A 4-month employee shows 7.00, not 21. |
| **Leave Salary Settlements Due** | Approved annual leave starting in the next N days with **no settlement**, and part-paid leave with **salary days still due**; shows earned days today, whether the barrier is met, days **payable now**. |
| **Gratuity Liability** | Per active employee as of a date: **if the company ends it** and **if the employee resigns** (e.g. KSA 7 years: resignation ≈ ⅔ of the other). An employee that cannot be calculated is **listed with the reason**, not dropped. Totals row. |
| **HR Payment Advice Queue** | §6.3. |

---

## 8. Not built / known limits (do not log these as bugs)
- The **2-year leave cycle** is stored on the Employee but does not change accrual or eligibility yet.
- A **late return** inside the leave balance only flags it: HR records the extension Leave Application by hand. An **early return** restores salary days and recovers the money but does not shorten the approved Leave Application (do that by hand).
- The daily alert `send_sick_leave_threshold_alerts` still reads the old Saudi-only Sick Leave document.
- Sick-pay daily rate is **total monthly salary ÷ 30** (all components). If sick pay should be on basic only, tell the developer.
- Qatar/Kuwait overtime and contribution rates and Kuwait resignation bands are marked **VERIFY** in the code; confirm with the client's legal adviser.
- The two-level approval is on the **HR Payment Advice**; see the sf_trading note in §6.2.

## 9. If something looks wrong
Note: employee, country, document name, what you did, what you expected, what you got (screenshot). Check **Error Log** (search "HR Suite") — failures that must not block a user (sick-pay deduction, rejection mail) are logged there. To undo a test: cancel the document (settlements, advices and leaves reverse their own entries); ledger rows are never deleted — post an **Adjustment**.

## 10. Test sign-off sheet
| Area | Cases | Result | Tester / date |
|---|---|---|---|
| Country policy | §1 | | |
| Gratuity | G1–G15 | | |
| Ledger & accrual | L1–L13 | | |
| Leave Salary Settlement | S1–S10, R1–R4 | | |
| Sick leave tiers | K1–K9 | | |
| Payment advice | P1–P12 | | |
| Expense Claim routing | X1–X5 | | |
| Reports | §7 | | |
