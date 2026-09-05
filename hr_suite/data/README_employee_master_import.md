# Employee Master — Data Import guide

Template: `employee_master_import_template.csv` (54 columns, verified against
`frappe.get_meta("Employee")` on sft-uat.enfonoerp.com — frappe 15.112.1, erpnext 15.113.0,
hrms 15.62.0).

The header row uses **fieldnames**, not labels. Frappe's importer accepts either
(`frappe/core/doctype/data_import/importer.py :: build_fields_dict_for_column_matching`),
and fieldnames are unambiguous — there are three Employee fields whose labels all contain
the word "Employee".

Row 2 of the template is a worked example showing the accepted formats.
**Delete it before importing.** Its `employee_number` is `EXAMPLE-DELETE-THIS-ROW` so it is
obvious in the Data Import preview if it is left in.

---

## 1. Create these masters FIRST — this is the real blocker

A Data Import fails the whole row when a Link column names a record that does not exist.
Checked on sft-uat:

| Column | Links to | On sft-uat today | Action |
|---|---|---|---|
| `grade` | Employee Grade | **0 records** | **Must be created before upload**, or leave the column blank |
| `health_insurance_provider` | Employee Health Insurance | **0 records** | **Must be created before upload**, or leave the column blank |
| `default_shift` | Shift Type | 1 (`Day Shift`) | Add the other shifts if employees are on them |
| `branch` | Branch | 4 (`SFSB`, `SFSS`, `SFWH`, `Test Branch -01`) | Confirm this is the full branch list |
| `department` | Department | 53 (suffixed `- SFB`, e.g. `Accounts - SFB`) | Use the **full** name including the abbreviation |
| `designation` | Designation | 31 | Add any missing job titles |
| `employment_type` | Employment Type | 8 (`Full-time`, `Part-time`, `Probation`, `Contract`, …) | ready |
| `holiday_list` | Holiday List | 3 (`Steel Force 2026`, `Steel Force 2025`, …) | ready |
| `nationality` | Country | 250 | ready — use the Frappe country name, e.g. `Bahrain`, `India` |
| `salutation` | Salutation | 9 (`Mr`, `Ms`, `Mrs`, `Dr`, …) | ready |
| `gender` | Gender | 7 (`Male`, `Female`, …) | ready |
| `company` | Company | 4 | use `Steel Force Trading WLL` |
| `payroll_cost_center` | Cost Center | 11 | ready |
| `salary_currency` | Currency | 149 | use `BHD` |
| `leave_approver`, `expense_approver`, `user_id` | User | 27 | the user must already exist |
| `reports_to` | Employee | 17 | **see §3 — import managers first** |

There is **no Default Holiday List on the Company**. Until one is set, every employee needs
`holiday_list` filled in, otherwise the Salary Slip cannot be created at all
(`erpnext/setup/doctype/employee/employee.py :: get_holiday_list_for_employee` throws).

---

## 2. Mandatory columns

`employee_number`, `first_name`, `gender`, `date_of_birth`, `date_of_joining`, `status`,
`company`.

`employee_number` becomes the **record ID**: HR Settings has
`emp_created_by = "Employee Number"`, so `hrms/overrides/employee_master.py :: autoname`
sets `name = employee_number`. Do not add a `name` or `ID` column, and do not add an
`employee` column — `employee` is set from `name` during validate.

Dates are `YYYY-MM-DD`. `status` must be one of `Active`, `Inactive`, `Suspended`, `Left`.

---

## 3. Import order

1. Create the missing masters in §1.
2. Import managers / anyone named in `reports_to`, with `reports_to` left blank.
3. Import everyone else, `reports_to` filled in.

`reports_to` is a Link to Employee and Employee is a tree doctype, so a row pointing at an
employee that has not been imported yet fails.

---

## 4. Column reference

### Identity
| Column | Type | Notes |
|---|---|---|
| `employee_number` | Data | **Mandatory.** Becomes the record ID. |
| `first_name` | Data | **Mandatory.** |
| `middle_name`, `last_name` | Data | |
| `salutation` | Link → Salutation | |
| `gender` | Link → Gender | **Mandatory.** |
| `date_of_birth` | Date | **Mandatory.** `YYYY-MM-DD`. |
| `marital_status` | Select | `Single`, `Married`, `Divorced`, `Widowed` |
| `blood_group` | Select | `A+`, `A-`, `B+`, `B-`, `AB+`, `AB-`, `O+`, `O-` |
| `national_id` | Data | **New (hr_suite).** CPR in Bahrain, National ID / Iqama in Saudi, Emirates ID in the UAE. Read by the WPS export and by the Payroll Preview identity check. |
| `nationality` | Link → Country | **New (hr_suite).** Reported on the WPS export; also drives the national/expatriate statutory split via `utils.get_employee_is_national()`. |
| `passport_number`, `date_of_issue`, `place_of_issue`, `valid_upto` | Data / Date | `valid_upto` is the passport expiry. |

### Employment & organisation
| Column | Type | Notes |
|---|---|---|
| `status` | Select | **Mandatory.** `Active` for the initial load. |
| `company` | Link → Company | **Mandatory.** |
| `date_of_joining` | Date | **Mandatory.** Drives service length, indemnity and leave accrual — do **not** copy the date of birth into it. |
| `employment_type` | Link → Employment Type | |
| `department`, `designation`, `branch` | Link | |
| `grade` | Link → Employee Grade | Master is empty — see §1. |
| `reports_to` | Link → Employee | See §3. |
| `work_country` | Select | **New (hr_suite).** `SA`, `AE`, `BH`, `IN`, `OM`. Leave blank to inherit the Company's country. Same codes as `Country Employment Contract.work_country`. |
| `hr_suite_employee_type` | Select | `National` or `Expatriate`. Sets the statutory contribution rate and the nationalization quota count. |
| `holiday_list` | Link → Holiday List | Required in practice — see §1. |
| `default_shift` | Link → Shift Type | |
| `attendance_device_id` | Data | Biometric / RF tag ID. |
| `final_confirmation_date` | Date | End of probation. |
| `contract_end_date` | Date | Limited contracts only. |
| `notice_number_of_days` | Int | |

### Payroll & Finance
| Column | Type | Notes |
|---|---|---|
| `salary_currency` | Link → Currency | `BHD`. |
| `salary_mode` | Select | `Bank`, `Cash`, `Cheque`. |
| `ctc` | Currency | Cost to Company. Does **not** create a Salary Structure Assignment — that is a separate import. |
| `hr_suite_gosi_salary` | Currency | Statutory contribution base (GOSI / SIO / GPSSA / PASI / EPF). |
| `payroll_cost_center` | Link → Cost Center | Where the payroll expense is posted. |
| `bank_name` | Data | Free text, not a Link. |
| `bank_ac_no` | Data | |
| `iban` | Data (IBAN) | Checksum-validated by Frappe — a wrong IBAN fails the row. |

### Contact
`cell_number`, `personal_email`, `company_email`, `prefered_contact_email`
(`Company Email` / `Personal Email` / `User ID`), `current_address`, `permanent_address`,
`person_to_be_contacted`, `relation`, `emergency_phone_number`.

### Optional
`health_insurance_provider` (Link → Employee Health Insurance, master empty),
`health_insurance_no`, `leave_approver`, `expense_approver`, `user_id` (all Link → User).

---

## 5. Not in this template, and why

* **Salary Structure Assignment** — a separate submittable document per employee. Payroll
  Preview reports "No submitted Salary Structure Assignment" as a *blocking* issue, so it
  must be loaded before the first payroll run.
* **Opening leave balances** — Leave Allocation, a separate submittable document.
* **Work permit / Iqama / LMRA** — the `Work Permit Iqama` doctype, one submittable record
  per permit, with its own expiry-alert scheduler. Permit number and expiry are deliberately
  **not** duplicated onto Employee.
* **Employee Documents** (`hr_suite_documents`) — a child table; import it separately with
  `hr_suite_documents.<fieldname>` columns, or fill it in on the form.
