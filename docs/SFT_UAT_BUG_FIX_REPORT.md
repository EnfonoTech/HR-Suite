# SFT UAT bug fixes: root cause, change and proof

Answers the consultant's *SFT HR Suite Bug Fix Specification* (13 Oct 2026). Every acceptance
case in it is a test in `hr_suite/hr_suite/test_sft_uat_fixes.py` (34 tests, all passing on the
scratch site `hrsuite-dev.localhost`, KSA and Bahrain). Run them with:

```
bench --site SITE run-tests --app hr_suite --module hr_suite.hr_suite.test_sft_uat_fixes
```

**Read this first.** `sft-uat.enfonoerp.com` was still running the first build (`439f0ea`) when the
consultant tested: PR #5 had never been deployed. Four of the nine bugs (1, 5, 8, 9) describe
features that this PR adds, so they are fixed *by deploying it*; the rest needed new work, below.
Nothing here has been run on `sft-uat` yet.

| # | Bug | Root cause | Fix (files) | Proof |
|---|---|---|---|---|
| 1 | KSA gratuity 21 days | Two causes. (a) On the deployed build the old hard-coded formula. (b) The Country Config form still showed the legacy field *Days/Year (Below Threshold)* seeded with **21** for Saudi Arabia (the UAE figure); nothing reads it now, but it is what a tester would see on the form (not checked on `sft-uat` itself). Slabs themselves were already 15 / 30 in PR #5. | Seed corrected to 15; legacy fields hidden and marked unused (`install.py`, `country_config.json`); patch `exact_resignation_thirds_and_ksa_legacy_days` fixes existing rows. Resignation factors stored as exact thirds (33.333333 / 66.666667, was 33.33 / 66.67, which lost 0.30 SAR on the spec's own example) (`policy_defaults.py`, `country_resignation_factor.json`). | `TestGratuityAcceptance`: 7 yrs terminated **27,000**; 3 yrs resigned **3,000**; under 2 yrs **0**; 12 yrs resigned **57,000**; Bahrain 5 yrs **21,000**, 12 yrs **63,000**. |
| 2 | "Can Be Taken From Leave" not visible | The field **did not exist** anywhere in HR Suite or HRMS, so it could not be found. Assumed meaning (confirmed by Sayanth): a leave type draws its days from another type's balance. | Custom Field on **Leave Policy Detail** (`install.py`, created on every migrate); `leave_application_rules.py`: balance check against the source type, ledger entry moved to it on approval, cancel returns the days; Leave Policy validation (no self-reference; drawing type gets *Allow Negative* with a message). | `TestCanBeTakenFrom`: policy row Emergency → Annual; 2 days taken, **Annual 7 → 5, Emergency unchanged**; over-draw refused; cancel returns days. |
| 3 | Balance shows 21 | The HR Suite **Leave Balance Report** computed `balance = annual entitlement − leave taken` (`leave_balance_report.py`), so an employee with one month's accrual showed 21. | Balance = accrued − taken; on the ledger engine it is HRMS's own balance, so it matches the ledger report. New columns *Annual Entitlement*, *Accrued To Date*, *Accruing This Month*. | `TestAccruedBalance`: 4 months → **7.00**; after 3 days **4.00**; report and ledger agree. |
| 4, 11 | 12-month minimum not enforced | On the deployed build the Leave Salary Settlement did not exist. In PR #5 it showed a shortfall and silently paid 0, and added a **second barrier of 30 earned days** that a 21-day employee reaches only after ~17 months. Nothing covered exit or leave taken before the minimum. | `leave_salary_settlement.py`: below the minimum service the settlement is **refused with the reason**; earned-days barrier default 0 (patch `relax_leave_salary_earned_days_barrier`); **Settlement Type = Final Settlement** pays accrued unused days on exit regardless of service (switch *Pay Accrued Leave On Exit…*); *Annual Leave Before Minimum Service* = Allow / Block / Unpaid (`leave_application_rules.py`). | `TestLeaveSalaryAcceptance`: 11 months refused ("service 334 of the 365 days needed"); 12 months pays **4,200** for 21 days; exit with 10.5 days pays **2,100**; exit switch off refuses; Block refuses; Unpaid books 3 × 200 = **600**. |
| 5 | Ledger report missing | Report, workspace link and HR User / HR Manager access all exist in PR #5 (not deployed). But it only listed accruals and settlements, so leave taken was missing and the running balance could not match the Leave Balance Report. | Report now has one row per transaction (Opening, Accrual, Adjustment, Settlement, **Leave Taken**, Encashment) with days in / out, running balance and a link to the source document. | `TestAccruedBalance`: 4 accrual rows of 1.75, running 1.75 … 7.00, then Leave Taken −3 → 4.00. |
| 6 | No Approve / Reject | HR Suite shipped **no workflow on Leave Application** (only on its legacy *Annual Leave* document), and the standard Status field gives no buttons. The cause on the consultant's site was not visible to me: if they built a workflow by hand the usual reasons are a role, a state or a condition mismatch, hence the doctor below. | `leave_workflow.py`: workflow **Leave Application Approval** (Open → Approved / Rejected, named Leave Approver or HR Manager, no self-approval, created inactive if the site already has an active one); `diagnose(application, user)` lists why buttons are missing. No alert e-mail on purpose (a PDF failure would undo the approval). | `TestApprovalWorkflow`: approver sees Approve / Reject; other approver and the employee (even as HR Manager) see none; approve takes the days; reject leaves the balance at 7. |
| 7 | KSA structure in BHD | HRMS leaves Salary Structure currency to the **user's default**, so a BHD user got BHD on a Saudi company. | `public/js/salary_structure.js` sets the company's currency; `salary_currency.py` defaults a blank one and warns on a mismatch; `mismatches()` lists structures to correct. | `TestCurrency`. Existing wrong structures still need amending by hand (submitted ones cannot change currency). |
| 8 | Settlement not available | Missing from the deployed build (PR #5). Exposed through workspace and HR Manager / HR User permissions. | See 4 and 11. | See 4 and 11. |
| 9 | Sick tiers wrong | Deployed build: older logic. PR #5 already split per day and re-split the year, but had no configurable window and **refused** to book a deduction for a month whose slip was already submitted (blocking a back-dated leave). | `sick_leave_tiers.py`: window per country (Leave Period / Calendar Year / Rolling 12 Months / Service Year); recalculates every sick leave from the affected date in date order; a closed month gets an **adjustment** (extra deduction or *Sick Leave Adjustment* earning) on the next open payroll date. | `TestSickAcceptance`: 0008 = 10 full + 30 at 75% (**750**); 0010 flips from full to 75% (**250**); closed November gets +250 then −250 on cancel; windows tested. |
| 10 | Annual leave not pro-rated | PR #5 ledger accrues 1.75 a month from joining, prorated in the joining month and stepping up at 5 years, but was off by default and the Leave Balance Report ignored it. | See 3. *Accrued To Date* now means everything earned since joining, plus *Accruing This Month* pro-rata. | `TestProRata`: joined 1 Jan 2025 → 17 accruals = 29.75, plus 0.70 on 12 Jun = **30.45**; joiner 9 Mar → 1.34; step-up 1.75 → 2.5. |

## Behaviour to know about

- **The monthly job credits at month end.** On 12 June the balance is 29.75; the 0.70 for June appears
  in *Accruing This Month* and is credited on 30 June. The consultant's "30.45" is the sum of both.
- **The three switches are still OFF on existing sites** (Leave Accrual Engine, Split Sick Leave, Expense
  Claim routing). Bugs 3, 5, 8, 9 and 10 only show on a country whose Leave Accrual Engine is *HR Suite
  Ledger*; switch Saudi Arabia (and Bahrain) on after importing opening balances.
- **New Country Config fields** (all with defaults that change nothing until chosen):
  *Pay Accrued Leave On Exit Below Minimum Service* (on), *Annual Leave Before Minimum Service* (Allow),
  *Sick Leave Pay Window* (Leave Period). *Minimum Earned Leave-Salary Days* is now 0.
- **Payroll adjustments were proved with the payroll calls mocked**, not against a real submitted Salary
  Slip. Run K11 in the UAT guide on `sft-uat` once deployed.
- Values the spec marks **verify** (Oman, Qatar, Kuwait, Bahrain SIO) are unchanged and still need the
  client's adviser.

## Regression checklist (spec's list)

| Item | Result |
|---|---|
| No hard-coded country values | Searched the leave, gratuity, payroll and settlement code: no 21 / 15 / 30 or currency code left outside seeds and the Employee GOSI preview (Saudi by design). `get_annual_leave_entitlement` now reads the country policy first. |
| Gratuity cases | Done for KSA (2, 3, 7, 12 yrs) and Bahrain. |
| Annual leave cases | New joiner, 1.45 years, crossing 5 years. |
| Balance report = ledger report | Tested. |
| Leave salary blocked / allowed / exit | Tested. |
| Sick leave | Tested including back-dated and closed month. |
| Workflow | Tested. |
| Currency KSA SAR / Bahrain BHD | Default-from-company tested for SAR; Bahrain follows the same rule by company. Not exercised against a real Bahrain company. |
| Cancel / amend reverse ledger and payroll | Settlement, sick leave, linked leave and unpaid-leave deductions have cancel tests. Amend has no dedicated test. |
| Fixtures survive `bench migrate` on a clean site | See the clean-site result in the PR. |

## Round 2: testing team's "B LIST" (16 Oct 2026)

| Finding | Root cause (read from the live `sft-uat` data) | Change |
|---|---|---|
| Leave application: no Submit button; approved leave missing from the Leave Salary Settlement list; sick leave tiers wrong (K10) | One cause. The testers created leaves as `fahad@enfono.com` and set **Status = Approved by hand**, because the workflow I shipped blocked its creator from approving (Frappe's self-approval test compares the approver with the document owner). The leaves (HR-LAP-2026-00008, 00009, 00010) sit at status Approved but **docstatus 0**: not submitted, so no Submit button (the workflow owns it), not in the settlement's approved list (it filters docstatus 1), and not counted by the sick-pay tiers (submitted only). The 40-day leave therefore started at day 0 (30 full + 10 at 75%) and the November leave never moved. | Workflow transitions no longer use the creator test; the employee-approves-own-leave rule is the condition on each transition. Setting Status by hand on a draft is refused with a message. Patch `reopen_leave_applications_stuck_before_submit` puts the stuck drafts back to Open so Approve submits them properly. |
| Leave allocation not automated, 30 instead of 21 | The 30-day allocation (HR-LAL-2026-00061) was made on 6 Oct by the old build's Leave Policy Assignment, before the engine existed. The testers then switched Saudi Arabia onto the ledger engine, but the monthly job runs 03:00 on the 1st and T13 has **0 ledger rows**, so nothing has accrued. The Leave Policy now carries Annual Leave = 0, correctly. | Country Config gets **Actions → Run Accrual Now**, which also lists allocations the ledger did not make (they add to the balance). Cancel HR-LAL-2026-00061 (or enter it as opening) first. |
| Saudi gratuity rule missing | (Voice note.) On the HRMS **Gratuity** form the *Gratuity Rule* list had only UAE and India rules; the Saudi slabs existed only on Country Config. | `gratuity_rules.py` creates HRMS rules from the slabs, after every migrate and never over an edited one: *Saudi Arabia / Oman / Qatar - Termination / End Of Contract* (marginal slabs, pro-rated years). Resignation reductions, caps and Bahrain's scheme end cannot be expressed in HRMS and stay in HR Suite's calculation. Tested against HRMS's own calculation: 7 yrs on 6,000 = 27,000. |
| Payment advice approval not working | (Screenshot + voice notes.) Three things: no approver is configured for Steel Force Trading WLL, so *Send for Approval* answers "No Approver"; with none configured, a direct Submit is by design the approval, so it showed Approved with no workflow; and the advice was not raised automatically from the settlement. The workflow itself is fine. | A submitted Leave Salary Settlement now raises its advice in the background (after commit, never inside the submit) and sends it for approval where approvers exist. Approvers on `sft-uat` set for the test (see below). |
