"""
leave_setup.py — turns the leave rules DECLARED in ``Country Config`` into a
working HRMS leave system, so that leave actually costs money at payroll time.

Before this module existed the ``Country Config.leave_types`` child rows were
seeded by ``install.py`` and read by nothing: 0 Leave Periods, 0 Leave Policies,
0 Leave Policy Assignments. A Leave Application therefore had no allocation
behind it and no effect on a Salary Slip.

What this provisions (all idempotent, wired into BOTH ``after_install`` and
``after_migrate`` — see ``hr_suite/install.py``):

  1. ``ensure_company_holiday_lists``  — every Company needs
     ``default_holiday_list``; ``Salary Slip`` cannot be produced without one.
  2. ``ensure_leave_periods``          — one Leave Period per Company per
     non-disabled Fiscal Year.
  3. ``sync_leave_types_from_country_config`` — the HRMS ``Leave Type`` masters,
     mapped ONTO the existing stock records where the name already matches
     (Annual / Sick / Maternity / Paternity Leave all ship with ERPNext), never
     duplicated beside them.
  4. ``ensure_leave_policies``         — a Leave Policy per country carrying the
     declared annual allocations.
  5. ``assign_leave_policy``           — assignment + allocation generation
     through the supported route (``Leave Policy Assignment``, which is what the
     stock ``Leave Control Panel`` also drives). Leave Allocations are NEVER
     written by hand here; core's ``grant_leave_alloc_for_employee`` creates
     them, so the Leave Ledger stays consistent.

STATUTORY DISCIPLINE — read before changing anything in this file
-----------------------------------------------------------------
This module encodes employment law. The ONLY statutory source it may read is
``Country Config`` — the client's own configured position. It therefore:

  * never hardcodes an entitlement, a rate or a band;
  * writes onto a ``Leave Type`` only the properties the config actually
    declares (days/year, carry-forward cap, optional flag, pay treatment) and
    leaves every other property of a stock Leave Type alone;
  * refuses to guess when two active countries declare different numbers for the
    same shared HRMS Leave Type — it records the conflict and writes nothing.

Sick-leave tiering (the known modelling problem)
------------------------------------------------
Bahrain sick leave is tiered by statute (a full-pay band, then a reduced-pay
band, then unpaid). ``Country Config`` declares it as ONE row of 55 days, which
cannot express a split. The MECHANISM for a split is built here — a
``Country Leave Type Row`` carries ``pay_treatment`` (Full Pay / Partially Paid /
Unpaid) and ``paid_fraction``, which map onto HRMS ``Leave Type.is_ppl`` +
``fraction_of_daily_salary_per_leave`` and ``Leave Type.is_lwp``; those are the
two fields ``Salary Slip.calculate_lwp_or_ppl_based_on_leave_application`` reads
when ``Payroll Settings.payroll_based_on == "Leave"``.

The DEFAULT is exactly what the config declares: one full-pay row. The split
(how many days in each band, and the reduced fraction) is NOT in the config and
is NOT invented here. To use it the client adds the extra bands as extra
``Country Config`` rows with their own ``frappe_leave_type_name``.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, getdate, today

from hr_suite.hr_suite.utils import country_name_to_code

# ``Country Leave Type Row.pay_treatment`` options.
PAY_FULL = "Full Pay"
PAY_PARTIAL = "Partially Paid"
PAY_UNPAID = "Unpaid"

# Words that carry no identity when matching a Holiday List to a Company.
_GENERIC_NAME_TOKENS = {
	"company",
	"holiday",
	"holidays",
	"list",
	"the",
	"and",
	"for",
	"llc",
	"wll",
	"ltd",
	"limited",
	"est",
	"spc",
	"bsc",
	"test",
	"group",
	"trading",
}


# ─── Entry point ───────────────────────────────────────────────────────────────


def setup_leave_management() -> dict:
	"""Provision the leave system from Country Config. Idempotent.

	Every step is isolated: a failure is logged and the remaining steps still
	run, because this is called from ``after_migrate`` and must never be able to
	abort a migration.
	"""
	summary = {}

	if not frappe.db.exists("DocType", "Country Config"):
		return summary

	for step in (
		ensure_company_holiday_lists,
		ensure_leave_periods,
		sync_leave_types_from_country_config,
		ensure_leave_policies,
	):
		try:
			summary[step.__name__] = step()
		except Exception:
			summary[step.__name__] = {"error": True}
			frappe.log_error(
				frappe.get_traceback(),
				"HR Suite: leave provisioning step {0} failed".format(step.__name__),
			)

	return summary


# ─── 1. Company default Holiday List ───────────────────────────────────────────


def ensure_company_holiday_lists() -> dict:
	"""Wire an existing Holiday List onto every Company that has none.

	``Salary Slip`` needs a holiday list to work out total working days, so a
	Company without ``default_holiday_list`` is a hard payroll blocker.

	WHICH list belongs to WHICH company is client configuration, not a statutory
	fact, so nothing is invented: this only connects lists that already exist.

	  1. ``Hr Suite Settings.default_holiday_list``, when the client has set it,
	     is used for every company that has none.
	  2. Otherwise a Holiday List whose name shares at least two identifying
	     words with the Company name (e.g. "Steel Force 2026" for
	     "Steel Force Trading WLL"), preferring one that covers today.

	A Company that matches nothing is left alone and reported — never guessed.
	"""
	result = {"set": {}, "unresolved": []}

	companies = frappe.get_all(
		"Company", fields=["name", "country", "default_holiday_list"], order_by="name"
	)
	pending = [c for c in companies if not c.default_holiday_list]
	if not pending:
		return result

	holiday_lists = frappe.get_all("Holiday List", fields=["name", "from_date", "to_date"])
	if not holiday_lists:
		result["unresolved"] = [c.name for c in pending]
		return result

	override = ""
	# Hr Suite Settings is a Single: it has no table, so frappe.db.has_column would
	# raise TableMissingError. Ask the meta whether the field exists instead.
	if frappe.get_meta("Hr Suite Settings").has_field("default_holiday_list"):
		override = cstr(frappe.db.get_single_value("Hr Suite Settings", "default_holiday_list") or "")
		if override and not frappe.db.exists("Holiday List", override):
			override = ""

	for company in pending:
		chosen = override or _match_holiday_list(company.name, holiday_lists)
		if not chosen:
			result["unresolved"].append(company.name)
			continue

		frappe.db.set_value("Company", company.name, "default_holiday_list", chosen)
		result["set"][company.name] = chosen

	return result


def _identity_tokens(name: str) -> set:
	tokens = set()
	for raw in cstr(name).replace("-", " ").replace("_", " ").split():
		token = "".join(ch for ch in raw.lower() if ch.isalnum())
		if len(token) < 3 or token.isdigit() or token in _GENERIC_NAME_TOKENS:
			continue
		tokens.add(token)
	return tokens


def _match_holiday_list(company: str, holiday_lists: list) -> str:
	"""Return the Holiday List whose name identifies it as this company's, or ''."""
	company_tokens = _identity_tokens(company)
	if not company_tokens:
		return ""

	run_date = getdate(today())
	candidates = []
	for hl in holiday_lists:
		overlap = len(company_tokens & _identity_tokens(hl.name))
		if overlap < 2:
			continue
		covers_today = bool(
			hl.from_date and hl.to_date and getdate(hl.from_date) <= run_date <= getdate(hl.to_date)
		)
		candidates.append((overlap, covers_today, cstr(hl.to_date), hl.name))

	if not candidates:
		return ""

	candidates.sort(reverse=True)
	return candidates[0][3]


# ─── 2. Leave Periods ──────────────────────────────────────────────────────────


def ensure_leave_periods() -> dict:
	"""One Leave Period per Company per non-disabled Fiscal Year."""
	result = {"created": [], "existing": 0}

	fiscal_years = frappe.get_all(
		"Fiscal Year",
		filters={"disabled": 0},
		fields=["name", "year_start_date", "year_end_date"],
		order_by="year_start_date",
	)
	if not fiscal_years:
		return result

	all_companies = frappe.get_all("Company", pluck="name")
	if not all_companies:
		return result

	run_date = getdate(today())

	for fy in fiscal_years:
		# A Fiscal Year may be restricted to a set of companies; an empty child
		# table means "all companies".
		scoped = frappe.get_all("Fiscal Year Company", filters={"parent": fy.name}, pluck="company")
		companies = [c for c in (scoped or all_companies) if c in all_companies]

		is_active = cint(getdate(fy.year_start_date) <= run_date <= getdate(fy.year_end_date))

		for company in companies:
			if frappe.db.exists(
				"Leave Period",
				{
					"company": company,
					"from_date": fy.year_start_date,
					"to_date": fy.year_end_date,
				},
			):
				result["existing"] += 1
				continue

			try:
				doc = frappe.get_doc(
					{
						"doctype": "Leave Period",
						"company": company,
						"from_date": fy.year_start_date,
						"to_date": fy.year_end_date,
						"is_active": is_active,
					}
				)
				doc.insert(ignore_permissions=True)
				result["created"].append(doc.name)
			except Exception:
				frappe.log_error(
					frappe.get_traceback(),
					"HR Suite: could not create Leave Period for {0} / {1}".format(company, fy.name),
				)

	return result


def get_leave_period(company: str, on_date: str | None = None) -> str:
	"""Return the Leave Period covering ``on_date`` (default today) for a company."""
	if not company:
		return ""

	target = getdate(on_date or today())
	return (
		frappe.db.get_value(
			"Leave Period",
			{
				"company": company,
				"from_date": ["<=", target],
				"to_date": [">=", target],
			},
			"name",
		)
		or ""
	)


# ─── 3. Leave Types ────────────────────────────────────────────────────────────


def get_active_country_codes() -> list:
	"""ISO-2 codes of the countries this site actually employs people in.

	Leave Types are GLOBAL in HRMS (one "Sick Leave" record for the whole site),
	so syncing every seeded Country Config would make five countries fight over
	the same master. Only countries that are actually in use are synced, and
	even then a disagreement between two of them is reported, not resolved.
	"""
	codes = set()

	if frappe.db.exists("DocType", "Country Employment Contract"):
		codes.update(
			cstr(c).strip().upper()
			for c in frappe.get_all(
				"Country Employment Contract",
				filters={"contract_status": "Active"},
				pluck="work_country",
				distinct=True,
			)
			if c
		)

	if frappe.db.has_column("Employee", "work_country"):
		for value in frappe.get_all(
			"Employee",
			filters={"status": "Active", "work_country": ["is", "set"]},
			pluck="work_country",
			distinct=True,
		):
			code = country_name_to_code(cstr(value).strip())
			if code:
				codes.add(code)

	companies = frappe.get_all("Employee", filters={"status": "Active"}, pluck="company", distinct=True)
	companies = [c for c in companies if c]
	if companies:
		for row in frappe.get_all("Company", filters={"name": ["in", companies]}, fields=["country"]):
			code = country_name_to_code(cstr(row.country).strip())
			if code:
				codes.add(code)

	if not codes:
		# No employees yet (fresh install): fall back to the companies that exist.
		for row in frappe.get_all("Company", fields=["country"]):
			code = country_name_to_code(cstr(row.country).strip())
			if code:
				codes.add(code)

	known = {
		cstr(r.country_code).strip().upper()
		for r in frappe.get_all("Country Config", filters={"is_active": 1}, fields=["country_code"])
	}

	return sorted(codes & known)


def _declared_rows(country_code: str) -> list:
	"""``Country Config.leave_types`` rows for one country, normalised."""
	name = frappe.db.get_value("Country Config", {"country_code": country_code}, "name")
	if not name:
		return []

	rows = frappe.get_all(
		"Country Leave Type Row",
		filters={"parent": name, "parenttype": "Country Config"},
		fields=["*"],
		order_by="idx",
	)

	normalised = []
	for row in rows:
		leave_type = cstr(row.get("frappe_leave_type_name") or row.get("leave_type_name")).strip()
		if not leave_type:
			continue
		normalised.append(
			frappe._dict(
				{
					"country_code": country_code,
					"leave_type": leave_type,
					"declared_name": cstr(row.get("leave_type_name")).strip(),
					"days_per_year": flt(row.get("days_per_year")),
					"gender_specific": cstr(row.get("gender_specific") or "All"),
					"is_optional": cint(row.get("is_optional")),
					"once_in_employment": cint(row.get("once_in_employment")),
					"max_carry_forward_days": flt(row.get("max_carry_forward_days")),
					# pay_treatment / paid_fraction are the tiering mechanism. A
					# row created before those fields existed reads as empty,
					# which means the config's plain full-pay entitlement.
					"pay_treatment": cstr(row.get("pay_treatment") or PAY_FULL),
					"paid_fraction": flt(row.get("paid_fraction")),
				}
			)
		)

	return normalised


def _pay_treatment_fields(row) -> dict | None:
	"""Map a declared pay treatment onto the HRMS Leave Type fields.

	``fraction_of_daily_salary_per_leave`` is the fraction of a day's salary that
	is still PAID: Salary Slip charges ``1 - fraction`` of a day as unpaid, so
	0.5 is half pay. Returns None when the declaration is unusable.
	"""
	treatment = row.pay_treatment or PAY_FULL

	if treatment == PAY_UNPAID:
		return {"is_lwp": 1, "is_ppl": 0, "fraction_of_daily_salary_per_leave": 0}

	if treatment == PAY_PARTIAL:
		fraction = flt(row.paid_fraction)
		if not 0 < fraction < 1:
			return None
		return {"is_lwp": 0, "is_ppl": 1, "fraction_of_daily_salary_per_leave": fraction}

	return {"is_lwp": 0, "is_ppl": 0, "fraction_of_daily_salary_per_leave": 0}


def sync_leave_types_from_country_config() -> dict:
	"""Create or update the HRMS Leave Type masters the active countries declare.

	Mapped onto the stock records by name — updating "Annual Leave" rather than
	creating "Annual Leave BH" beside it. Only the properties Country Config
	declares are written; everything else on a stock Leave Type is left as-is.
	"""
	result = {"created": [], "updated": [], "unchanged": [], "conflicts": [], "failed": []}

	by_type = {}
	for code in get_active_country_codes():
		for row in _declared_rows(code):
			by_type.setdefault(row.leave_type, []).append(row)

	for leave_type, rows in sorted(by_type.items()):
		values = _resolve_declared_values(leave_type, rows, result)
		exists = frappe.db.exists("Leave Type", leave_type)

		try:
			if not exists:
				doc = frappe.get_doc({"doctype": "Leave Type", "leave_type_name": leave_type})
				for field, value in (values or {}).items():
					doc.set(field, value)
				doc.insert(ignore_permissions=True)
				result["created"].append(leave_type)
				continue

			if not values:
				result["unchanged"].append(leave_type)
				continue

			doc = frappe.get_doc("Leave Type", leave_type)
			changed = {
				field: value for field, value in values.items() if flt(doc.get(field)) != flt(value)
			}
			if not changed:
				result["unchanged"].append(leave_type)
				continue

			for field, value in changed.items():
				doc.set(field, value)
			doc.save(ignore_permissions=True)
			result["updated"].append({"leave_type": leave_type, "changed": changed})
		except Exception:
			result["failed"].append(leave_type)
			frappe.log_error(
				frappe.get_traceback(),
				"HR Suite: could not sync Leave Type {0}".format(leave_type),
			)

	return result


def _resolve_declared_values(leave_type: str, rows: list, result: dict) -> dict | None:
	"""Collapse every active country's declaration for one shared Leave Type.

	Returns the fields to write, or None when the countries disagree — in which
	case nothing is written and the conflict is reported, because picking one
	country's number over another's would be inventing law for the loser.
	"""
	distinct = {
		(
			row.days_per_year,
			row.max_carry_forward_days,
			row.is_optional,
			row.pay_treatment,
			row.paid_fraction,
		)
		for row in rows
	}

	if len(distinct) > 1:
		result["conflicts"].append(
			{
				"leave_type": leave_type,
				"declared_by": [
					{
						"country": row.country_code,
						"days_per_year": row.days_per_year,
						"max_carry_forward_days": row.max_carry_forward_days,
						"pay_treatment": row.pay_treatment,
					}
					for row in rows
				],
			}
		)
		return None

	row = rows[0]
	pay_fields = _pay_treatment_fields(row)
	if pay_fields is None:
		result["conflicts"].append(
			{
				"leave_type": leave_type,
				"country": row.country_code,
				"reason": "Partially Paid declared without a paid fraction strictly between 0 and 1",
			}
		)
		pay_fields = {}

	values = {
		"is_carry_forward": cint(row.max_carry_forward_days > 0),
		"maximum_carry_forwarded_leaves": row.max_carry_forward_days,
		"is_optional_leave": row.is_optional,
	}
	if row.days_per_year > 0:
		# Caps the allocation. Two core rules read this field and they pull in opposite
		# directions, so the cap must cover the entitlement AND the carry-forward:
		#   * Leave Policy.validate rejects annual_allocation > max_leaves_allowed, so the
		#     cap can never be below the declared entitlement; and
		#   * LeaveAllocation.limit_carry_forward_based_on_max_allowed_leaves (hrms
		#     leave_allocation.py:255) SILENTLY clamps total_leaves_allocated — new plus
		#     carried — down to max_leaves_allowed, and zeroes unused_leaves with it.
		# A cap of exactly days_per_year therefore destroys the carry-forward the config
		# declares: with Bahrain's Annual Leave 30 + carry-forward 30, next year's
		# allocation came out 30 total / 0 carried instead of 60 / 30, with no error.
		# Both terms are Country Config figures; nothing statutory is invented here.
		values["max_leaves_allowed"] = row.days_per_year + max(row.max_carry_forward_days, 0)

	values.update(pay_fields)
	return values


# ─── 4. Leave Policies ─────────────────────────────────────────────────────────


def get_policy_titles(country_code: str) -> dict:
	"""Policy titles for a country, keyed by the gender they serve."""
	country_name = (
		frappe.db.get_value("Country Config", {"country_code": country_code}, "country_name")
		or country_code
	)
	return {
		"All": _("{0} Leave Policy").format(country_name),
		"Male": _("{0} Leave Policy - Male").format(country_name),
		"Female": _("{0} Leave Policy - Female").format(country_name),
	}


def _policy_details(country_code: str, gender: str) -> list:
	"""Annual allocations for a country/gender, straight from Country Config.

	Excluded on purpose:
	  * ``once_in_employment`` rows (e.g. Hajj Leave) — a once-in-a-career
	    entitlement is not an annual allocation, and putting it in an annual
	    policy would re-grant it every single year. The Leave Type is still
	    created, so it can be allocated once, by hand, when it is taken.
	  * unpaid rows — core's ``grant_leave_alloc_for_employee`` skips ``is_lwp``
	    types anyway, and HRMS refuses to mark a Leave Type unpaid while an
	    allocation for it is live.
	"""
	details = []
	seen = set()
	for row in _declared_rows(country_code):
		if row.once_in_employment or row.days_per_year <= 0:
			continue
		if row.pay_treatment == PAY_UNPAID:
			continue
		if row.gender_specific not in ("All", "{0} Only".format(gender)):
			continue
		if row.leave_type in seen:
			continue
		seen.add(row.leave_type)
		details.append({"leave_type": row.leave_type, "annual_allocation": row.days_per_year})

	return details


def ensure_leave_policies() -> dict:
	"""One Leave Policy per country, plus gender variants where the config needs them.

	HRMS ``Leave Type`` has no gender field, and a Leave Policy Assignment
	allocates EVERY type in its policy — so ``gender_specific`` can only be
	honoured by keeping the gendered entitlements in separate policies and
	choosing the right one per employee (see ``resolve_leave_policy``).
	"""
	result = {"created": [], "existing": [], "drifted": [], "failed": []}

	for code in get_active_country_codes():
		rows = _declared_rows(code)
		if not rows:
			continue

		titles = get_policy_titles(code)
		wanted = {"All": _policy_details(code, "All")}

		for gender in ("Male", "Female"):
			if any(row.gender_specific == "{0} Only".format(gender) for row in rows):
				wanted[gender] = _policy_details(code, gender)

		for gender, details in wanted.items():
			title = titles[gender]
			if not details:
				continue

			existing = frappe.db.get_value("Leave Policy", {"title": title, "docstatus": 1}, "name")
			if existing:
				if _policy_differs(existing, details):
					# The policy is submitted and may already be assigned.
					# Amending it silently would change people's entitlements, so
					# report the drift and leave the document alone.
					result["drifted"].append({"policy": existing, "title": title})
				else:
					result["existing"].append(existing)
				continue

			try:
				doc = frappe.get_doc(
					{"doctype": "Leave Policy", "title": title, "leave_policy_details": details}
				)
				doc.insert(ignore_permissions=True)
				doc.submit()
				result["created"].append(doc.name)
			except Exception:
				result["failed"].append(title)
				frappe.log_error(
					frappe.get_traceback(),
					"HR Suite: could not create Leave Policy {0}".format(title),
				)

	return result


def _policy_differs(policy: str, details: list) -> bool:
	current = {
		row.leave_type: flt(row.annual_allocation)
		for row in frappe.get_all(
			"Leave Policy Detail",
			filters={"parent": policy, "parenttype": "Leave Policy"},
			fields=["leave_type", "annual_allocation"],
		)
	}
	wanted = {d["leave_type"]: flt(d["annual_allocation"]) for d in details}
	return current != wanted


def resolve_leave_policy(country_code: str, gender: str | None = None) -> str:
	"""The Leave Policy an employee of this country/gender should be assigned."""
	titles = get_policy_titles(country_code)

	for key in (cstr(gender).strip(), "All"):
		title = titles.get(key)
		if not title:
			continue
		name = frappe.db.get_value("Leave Policy", {"title": title, "docstatus": 1}, "name")
		if name:
			return name

	return ""


# ─── 5. Assignment + allocation (the supported route) ──────────────────────────


@frappe.whitelist()
def assign_leave_policy(
	employees: str | list | None = None,
	company: str | None = None,
	leave_period: str | None = None,
	carry_forward: int | str = 0,
) -> dict:
	"""Assign the country Leave Policy and generate allocations for employees.

	Allocations are produced by core's ``LeavePolicyAssignment.on_submit`` ->
	``grant_leave_alloc_for_employee``, i.e. exactly what the desk's Leave
	Control Panel does. Nothing here writes a Leave Allocation directly, so the
	Leave Ledger, carry-forward and expiry all behave as HRMS expects.

	Returns ``{"assigned": [...], "skipped": [...], "failed": [...]}``.
	"""
	from hrms.hr.doctype.leave_policy_assignment.leave_policy_assignment import create_assignment

	if not frappe.has_permission("Leave Policy Assignment", "create"):
		frappe.throw(_("Not permitted to create Leave Policy Assignments"), frappe.PermissionError)

	if isinstance(employees, str):
		employees = json.loads(employees) if employees.strip().startswith("[") else [employees]

	carry_forward = cint(carry_forward)
	company = cstr(company).strip()

	if not employees:
		if not company:
			frappe.throw(_("Provide either a list of employees or a company"))
		employees = frappe.get_all(
			"Employee", filters={"status": "Active", "company": company}, pluck="name"
		)

	employees = [cstr(e).strip() for e in employees if cstr(e).strip()]
	if not employees:
		return {"assigned": [], "skipped": [], "failed": []}

	if leave_period:
		leave_period = cstr(leave_period).strip()
		if not frappe.db.exists("Leave Period", leave_period):
			frappe.throw(_("Leave Period {0} does not exist").format(leave_period))

	result = {"assigned": [], "skipped": [], "failed": []}

	for employee in employees:
		try:
			outcome = _assign_one(employee, leave_period, carry_forward, create_assignment)
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				"HR Suite: Leave Policy Assignment failed for {0}".format(employee),
			)
			result["failed"].append(employee)
			continue

		if outcome.get("skipped"):
			result["skipped"].append({"employee": employee, "reason": outcome["skipped"]})
		else:
			result["assigned"].append(outcome)

	return result


def _assign_one(employee: str, leave_period: str | None, carry_forward: int, create_assignment):
	from hr_suite.hr_suite.utils import get_employee_work_country

	emp = frappe.db.get_value("Employee", employee, ["company", "gender", "status"], as_dict=True)
	if not emp:
		return {"skipped": _("Employee not found")}

	period = leave_period or get_leave_period(emp.company)
	if not period:
		return {"skipped": _("No Leave Period covers today for {0}").format(emp.company)}

	country_code = get_employee_work_country(employee)
	policy = resolve_leave_policy(country_code, emp.gender)
	if not policy:
		return {"skipped": _("No Leave Policy for country {0}").format(country_code or "?")}

	from_date, to_date = frappe.db.get_value("Leave Period", period, ["from_date", "to_date"])

	if frappe.db.exists(
		"Leave Policy Assignment",
		{
			"employee": employee,
			"docstatus": 1,
			"effective_from": ["<=", to_date],
			"effective_to": [">=", from_date],
		},
	):
		return {"skipped": _("Already assigned for this period")}

	data = frappe._dict(
		{
			"assignment_based_on": "Leave Period",
			"leave_policy": policy,
			"leave_period": period,
			"effective_from": from_date,
			"effective_to": to_date,
			"carry_forward": carry_forward,
		}
	)

	savepoint = "before_hr_suite_leave_assignment"
	frappe.db.savepoint(savepoint)
	try:
		assignment = create_assignment(employee, data)
		assignment.submit()
	except Exception:
		frappe.db.rollback(save_point=savepoint)
		raise

	allocations = frappe.get_all(
		"Leave Allocation",
		filters={"leave_policy_assignment": assignment.name, "docstatus": 1},
		fields=["name", "leave_type", "new_leaves_allocated"],
	)

	return {
		"employee": employee,
		"assignment": assignment.name,
		"leave_policy": policy,
		"leave_period": period,
		"allocations": allocations,
	}


# ─── Status ────────────────────────────────────────────────────────────────────


@frappe.whitelist()
def get_leave_setup_status() -> dict:
	"""Read-only summary of what is provisioned — safe to call from the desk."""
	if not frappe.has_permission("Leave Type", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	countries = get_active_country_codes()

	return {
		"active_countries": countries,
		"companies_without_holiday_list": frappe.get_all(
			"Company", filters={"default_holiday_list": ["in", [None, ""]]}, pluck="name"
		),
		"leave_periods": frappe.db.count("Leave Period"),
		"leave_policies": frappe.get_all(
			"Leave Policy", filters={"docstatus": 1}, fields=["name", "title"]
		),
		"leave_policy_assignments": frappe.db.count("Leave Policy Assignment", {"docstatus": 1}),
		"leave_allocations": frappe.db.count("Leave Allocation", {"docstatus": 1}),
		"declared_leave_types": {
			code: [r.leave_type for r in _declared_rows(code)] for code in countries
		},
	}
