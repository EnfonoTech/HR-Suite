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
  6. ``roll_forward_leave_periods``    — next year's Leave Period, and this
     year's Leave Policy Assignment for everyone who held last year's, so a
     balance crosses the year boundary instead of dying with it.

Monthly accrual (2.5 days a month, not 30 days in January)
----------------------------------------------------------
HRMS already implements accrual and hr_suite does NOT reimplement it: a
``Leave Type`` with ``is_earned_leave`` is topped up on its ONE year-long
allocation by the daily scheduled job ``hrms.hr.utils.allocate_earned_leaves``,
which divides the Leave Policy's ``annual_allocation`` by the frequency, rounds,
and writes an additional Leave Ledger Entry.

All this module does is switch that on from what Country Config declares —
``Country Leave Type Row.accrual_frequency`` first, then the country-wide
``Country Config.leave_accrual_frequency``, and no accrual at all when neither
says anything. A row declaring ``"None"`` is granted whole: sick, maternity and
once-in-employment leave are entitlements you either have or do not have, and
accruing them by twelfths would leave a January sick day uncovered.

The one grant model that must NEVER run beside it is a second allocation for the
same days — see ``check_double_allocation_risk``, and the retired
``hr_suite.hr_suite.tasks.allocate_monthly_leave`` it replaced.

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
from frappe.utils import add_days, add_years, cint, cstr, flt, get_last_day, getdate, today

from hr_suite.hr_suite.utils import assert_doctype_permissions, country_name_to_code

# ``Country Leave Type Row.pay_treatment`` options.
PAY_FULL = "Full Pay"
PAY_PARTIAL = "Partially Paid"
PAY_UNPAID = "Unpaid"

# ``Country Leave Type Row.accrual_frequency`` / ``Country Config.leave_accrual_frequency``.
# "None" is a DECLARATION — this entitlement is granted whole — and is not the same as a
# blank, which declares nothing at all and leaves the Leave Type alone.
ACCRUAL_NONE = "None"

# ``Leave Type.earned_leave_frequency`` options, i.e. the keys
# ``hrms.hr.utils.check_effective_date`` indexes its expected-date map by.
ACCRUAL_FREQUENCIES = ("Monthly", "Quarterly", "Half-Yearly", "Yearly")

# ``Leave Type.allocate_on_day`` options. "Date of Joining" is only a key of the Monthly
# branch of that same map — see ``_accrual_fields``.
ALLOCATE_ON_DAY_OPTIONS = ("First Day", "Last Day", "Date of Joining")
DEFAULT_ALLOCATE_ON_DAY = "Last Day"

# ``Leave Type.rounding`` options ("" means no rounding).
ROUNDING_OPTIONS = ("0.25", "0.5", "1.0")

# The Leave Type fields that switch HRMS earned-leave accrual on.
ACCRUAL_FIELDS = ("is_earned_leave", "earned_leave_frequency", "allocate_on_day", "rounding")

# How early next year's Leave Period is opened, in days before the current one ends.
PERIOD_ROLL_FORWARD_LEAD_DAYS = 60

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
		# Last, because it reads the Leave Types and Policies the steps above wrote.
		report_double_allocation_risk,
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

	accrual = _country_accrual_defaults(country_code)

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
					# Accrual is declared BY THE ROW, never by the country.
					#
					# The country-wide frequency used to cascade onto every row that said
					# nothing, which flipped Sick (120 days in Bahrain), Maternity and
					# Paternity leave to HRMS earned leave: an employee would have held
					# 10 of their 120 sick days in January and been refused the eleventh
					# on the day they were ill, because the rest had not been "earned" yet.
					# Only leave that is earned by serving another month accrues, and the
					# row is the only place that distinction is recorded.
					"accrual_frequency": cstr(row.get("accrual_frequency") or "").strip(),
					"accrual_source": "row" if cstr(row.get("accrual_frequency")).strip() else "",
					"accrual_on_day": cstr(accrual.leave_accrual_on_day or "").strip(),
					"accrual_rounding": cstr(accrual.leave_accrual_rounding or "").strip(),
					"carry_forward_expiry_days": cint(accrual.carry_forward_expiry_days),
				}
			)
		)

	return normalised


def _country_accrual_defaults(country_code: str) -> frappe._dict:
	"""The country-wide accrual declaration, or empties when those fields are absent.

	Read through the meta rather than assumed: this module runs from
	``after_migrate``, and a bench that has not yet synced the Country Config changes
	would otherwise take the whole leave provisioning down with an unknown-column error.
	"""
	wanted = (
		"leave_accrual_frequency",
		"leave_accrual_on_day",
		"leave_accrual_rounding",
		"carry_forward_expiry_days",
	)
	defaults = frappe._dict({field: "" for field in wanted})

	meta = frappe.get_meta("Country Config")
	present = [field for field in wanted if meta.has_field(field)]
	if not present:
		return defaults

	row = frappe.db.get_value("Country Config", {"country_code": country_code}, present, as_dict=True)
	if row:
		defaults.update(row)

	return defaults


def _accrual_fields(row) -> dict:
	"""Map a declared accrual onto the HRMS earned-leave fields of ``Leave Type``.

	Returns ``{}`` when the config declares nothing at all, so a Leave Type nobody has
	taken a decision about keeps whatever it already has.
	"""
	frequency = cstr(row.accrual_frequency).strip()

	# An entitlement that cannot be EARNED by serving another month is kept whole
	# whatever the country declares: a once-in-a-career grant (Hajj), an unpaid type
	# (core allocates none) and a zero-day row. Dripping those out by twelfths would
	# leave the entitlement unavailable on the day it is actually needed.
	if row.once_in_employment or row.days_per_year <= 0 or row.pay_treatment == PAY_UNPAID:
		frequency = ACCRUAL_NONE if frequency else ""

	if not frequency:
		return {}

	if frequency == ACCRUAL_NONE:
		return {"is_earned_leave": 0}

	if frequency not in ACCRUAL_FREQUENCIES:
		return {}

	values = {"is_earned_leave": 1, "earned_leave_frequency": frequency}

	# ``hrms.hr.utils.check_effective_date`` indexes a literal dict as
	# ``[frequency][allocate_on_day]``, and only its Monthly branch carries a
	# "Date of Joining" key. An empty day, or that day on any other frequency, raises
	# KeyError inside the DAILY scheduled job and stops the accrual of every leave
	# type on the site, not just this one.
	on_day = cstr(row.accrual_on_day).strip()
	if on_day not in ALLOCATE_ON_DAY_OPTIONS:
		on_day = DEFAULT_ALLOCATE_ON_DAY
	if on_day == "Date of Joining" and frequency != "Monthly":
		on_day = DEFAULT_ALLOCATE_ON_DAY
	values["allocate_on_day"] = on_day

	rounding = cstr(row.accrual_rounding).strip()
	if rounding in ROUNDING_OPTIONS:
		values["rounding"] = rounding

	return values


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
			values = _drop_accrual_for_compensatory(leave_type, doc, values, result)
			values = _defer_accrual_while_already_granted(leave_type, doc, values, result)
			changed = {
				field: value
				for field, value in values.items()
				if _value_changed(doc.get(field), value)
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
			# Accrual is part of the declaration: one country accruing Annual Leave
			# monthly while another grants it whole is the same kind of disagreement
			# as two different day counts, and is resolved the same way — not at all.
			row.accrual_frequency,
			row.accrual_on_day,
			row.accrual_rounding,
			row.carry_forward_expiry_days,
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
	values.update(_accrual_fields(row))

	# Only meaningful once carry-forward is on, and an Int cannot tell "no expiry"
	# from "not configured": a 0 is therefore left alone rather than written.
	if values["is_carry_forward"] and cint(row.carry_forward_expiry_days) > 0:
		values["expire_carry_forwarded_leaves_after_days"] = cint(row.carry_forward_expiry_days)

	return values


def _value_changed(current, wanted) -> bool:
	"""Has this Leave Type field drifted from what the config declares?

	The Select fields have to be compared as TEXT. Comparing them the way the numeric
	fields are compared silently reads flt("Monthly") as 0.0, which equals flt("Yearly"),
	so every accrual change looked like no change and the Leave Type was never switched
	over — the sync reported "unchanged" and wrote nothing.
	"""
	if isinstance(wanted, str):
		return cstr(current).strip() != wanted

	return flt(current) != flt(wanted)


def _drop_accrual_for_compensatory(leave_type: str, doc, values: dict, result: dict) -> dict:
	"""Never set ``is_earned_leave`` on a compensatory type.

	``LeaveType.validate_leave_types`` throws when both flags are on, and that throw
	would abort the whole sync inside ``after_migrate``. The conflict is reported and
	the rest of the declaration is still applied.
	"""
	if not (cint(doc.is_compensatory) and cint(values.get("is_earned_leave"))):
		return values

	result["conflicts"].append(
		{
			"leave_type": leave_type,
			"reason": _("Accrual declared for a Leave Type that HRMS marks compensatory"),
		}
	)
	return {field: value for field, value in values.items() if field not in ACCRUAL_FIELDS}


def _defer_accrual_while_already_granted(leave_type: str, doc, values: dict, result: dict) -> dict:
	"""Do not switch a leave type to accrual while employees still hold this year's grant.

	HRMS accrues onto the allocation that is live TODAY, and stops only at the Leave
	Policy's annual allocation — it has no notion of "these days were already handed
	over". So flipping ``is_earned_leave`` mid-period on a site whose employees hold a
	grant made by a Leave Policy Assignment credits accrued days ON TOP of that grant:
	a joiner pro-rated to 8 days in July would be topped up to the full 30 by December,
	and those extra days are real money the moment they are encashed or paid as leave
	salary.

	The switch is therefore deferred until no live allocation is left, which in practice
	means the next Leave Period, and the deferral is reported rather than hidden. A site
	that has adjusted its allocations by hand — or a test site — can override it with
	``Hr Suite Settings.accrual_switch_over_now``.
	"""
	if not cint(values.get("is_earned_leave")) or cint(doc.is_earned_leave):
		# Nothing to switch on, or it is already on: accrual is then the status quo and
		# the allocations live beside it were created knowing that.
		return values

	if cint(frappe.db.get_single_value("Hr Suite Settings", "accrual_switch_over_now")):
		return values

	live = frappe.db.count(
		"Leave Allocation",
		{
			"docstatus": 1,
			"leave_type": leave_type,
			"from_date": ["<=", today()],
			"to_date": [">=", today()],
		},
	)
	if not live:
		return values

	result["conflicts"].append(
		{
			"leave_type": leave_type,
			"reason": _(
				"Monthly accrual is not switched on yet: {0} employee(s) still hold a live "
				"allocation of {1} for this leave period, and HRMS would credit accrued days on "
				"top of it. It switches over by itself once those allocations end, or "
				"immediately if you tick Switch Leave Types to Accrual Immediately in "
				"Hr Suite Settings."
			).format(live, leave_type),
		}
	)
	return {field: value for field, value in values.items() if field not in ACCRUAL_FIELDS}


# ─── 3b. The two-grant-models guard ────────────────────────────────────────────


def get_earned_leave_types() -> list:
	"""Leave Types HRMS will accrue, i.e. the ones the daily scheduler picks up."""
	return frappe.get_all(
		"Leave Type",
		filters={"is_earned_leave": 1},
		fields=["name", "earned_leave_frequency", "allocate_on_day", "rounding", "max_leaves_allowed"],
		order_by="name",
	)


def check_double_allocation_risk(as_on: str | None = None) -> dict:
	"""Report every way a leave type could end up granted twice for the same year.

	Accrual only works if HRMS is the ONLY thing granting the days. A type that is
	accruing 2.5 days a month AND holding an allocation that was already granted in
	full is not a rounding problem — it is a year of leave issued twice.

	Reports, never throws: this runs from ``after_migrate`` and from a scheduled job,
	and an exception in either place is far more expensive than the finding.

	Returns ``{"ok": bool, "earned_leave_types": [...], "findings": [...]}``.
	"""
	run_date = getdate(as_on or today())
	findings = []

	earned = get_earned_leave_types()
	earned_names = [row.name for row in earned]

	if not earned_names:
		return {"ok": True, "earned_leave_types": [], "findings": findings}

	# The retired month-window job. Its switch being on means somebody can still turn a
	# second grant model loose on types HRMS is already accruing.
	if cint(frappe.db.get_single_value("Hr Suite Settings", "monthly_leave_allocation_enabled")):
		findings.append(
			{
				"issue": "monthly_grant_job_enabled",
				"detail": _(
					"Hr Suite Settings has monthly leave allocation switched on while {0} "
					"leave type(s) already accrue through HRMS."
				).format(len(earned_names)),
				"leave_types": earned_names,
			}
		)

	# One pass over Leave Policy Detail: the scheduler divides annual_allocation by the
	# frequency, so a type with no policy figure accrues exactly nothing.
	annual_by_policy = {}
	annual_by_type = {}
	submitted_policies = set(frappe.get_all("Leave Policy", filters={"docstatus": 1}, pluck="name"))
	for detail in frappe.get_all(
		"Leave Policy Detail",
		filters={"parenttype": "Leave Policy", "leave_type": ["in", earned_names]},
		fields=["parent", "leave_type", "annual_allocation"],
	):
		if detail.parent not in submitted_policies:
			continue
		annual_by_policy[(detail.parent, detail.leave_type)] = flt(detail.annual_allocation)
		annual_by_type[detail.leave_type] = max(
			flt(detail.annual_allocation), annual_by_type.get(detail.leave_type, 0.0)
		)

	orphaned = [name for name in earned_names if name not in annual_by_type]
	if orphaned:
		findings.append(
			{
				"issue": "accrues_without_a_policy_figure",
				"detail": _(
					"No submitted Leave Policy carries an annual allocation for these accruing "
					"leave types, so the scheduler has nothing to divide and credits zero days."
				),
				"leave_types": orphaned,
			}
		)

	granted_whole = []
	month_windows = []
	for alloc in frappe.get_all(
		"Leave Allocation",
		filters={
			"docstatus": 1,
			"leave_type": ["in", earned_names],
			"from_date": ["<=", run_date],
			"to_date": [">=", run_date],
		},
		fields=[
			"name",
			"employee",
			"leave_type",
			"leave_policy",
			"from_date",
			"to_date",
			"new_leaves_allocated",
		],
	):
		annual = annual_by_policy.get((alloc.leave_policy, alloc.leave_type)) or annual_by_type.get(
			alloc.leave_type
		)
		if annual and flt(alloc.new_leaves_allocated) >= annual:
			granted_whole.append(alloc)

		# The shape the retired job produced: a window inside a single calendar month.
		# Days allocated like that expire with the month and can never be carried.
		if getdate(alloc.to_date) <= get_last_day(alloc.from_date):
			month_windows.append(alloc)

	if granted_whole:
		findings.append(
			{
				"issue": "already_granted_in_full",
				"detail": _(
					"{0} live allocation(s) already hold the whole annual entitlement for a leave "
					"type that now accrues. HRMS will not accrue on top of them — those employees "
					"keep the year they were granted up front, and accrual starts next period."
				).format(len(granted_whole)),
				"count": len(granted_whole),
				"examples": [
					{"allocation": a.name, "employee": a.employee, "leave_type": a.leave_type}
					for a in granted_whole[:5]
				],
			}
		)

	if month_windows:
		findings.append(
			{
				"issue": "month_window_allocation",
				"detail": _(
					"{0} live allocation(s) cover a single month. Days allocated that way expire "
					"at month end, so they can neither be carried forward nor spent later."
				).format(len(month_windows)),
				"count": len(month_windows),
				"examples": [
					{
						"allocation": a.name,
						"employee": a.employee,
						"leave_type": a.leave_type,
						"from_date": cstr(a.from_date),
						"to_date": cstr(a.to_date),
					}
					for a in month_windows[:5]
				],
			}
		)

	return {"ok": not findings, "earned_leave_types": earned_names, "findings": findings}


def report_double_allocation_risk(as_on: str | None = None) -> dict:
	"""``check_double_allocation_risk`` plus somewhere for the answer to land.

	The desk gets a msgprint; a scheduler run has no session to print into, so the
	same text goes to the Error Log where an administrator will actually find it.
	"""
	report = check_double_allocation_risk(as_on)
	if report["ok"]:
		return report

	lines = [cstr(finding["detail"]) for finding in report["findings"]]
	message = _("Leave accrual and a second grant model are both live:") + "\n" + "\n".join(lines)

	frappe.log_error(message, "HR Suite: leave may be allocated twice")
	if getattr(frappe.local, "request", None):
		frappe.msgprint(message, title=_("Leave Allocation Warning"), indicator="orange")

	return report


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


def assign_leave_policy_for_employee(employee: str, leave_period: str | None = None,
                                     carry_forward: int = 0) -> dict:
	"""Grant ONE employee their leave through the supported route.

	Separate from the whitelisted ``assign_leave_policy`` on purpose: this runs as
	a side effect of creating an Employee, where the user has already proved their
	authority by creating the record. The HTTP permission gate on the endpoint
	would otherwise stop onboarding for a role that may add staff but not assign
	leave policies.
	"""
	from hrms.hr.doctype.leave_policy_assignment.leave_policy_assignment import create_assignment

	return _assign_one(employee, leave_period, cint(carry_forward), create_assignment)


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


# ─── 6. Year roll-forward ──────────────────────────────────────────────────────


def _next_period_dates(from_date, to_date) -> tuple:
	"""The period that starts the day the given one ends.

	Built by adding a year to the NEW start rather than to both ends, so the periods
	are contiguous with no gap and no overlap — a leap day inside the old window
	otherwise shifts the new one and ``LeavePeriod.validate`` rejects it as an overlap.
	"""
	next_from = add_days(getdate(to_date), 1)
	next_to = add_days(add_years(next_from, 1), -1)
	return next_from, next_to


def _latest_period(company: str):
	rows = frappe.get_all(
		"Leave Period",
		filters={"company": company},
		fields=["name", "from_date", "to_date"],
		order_by="to_date desc",
		limit=1,
	)
	return rows[0] if rows else None


def _period_covering(company: str, on_date):
	rows = frappe.get_all(
		"Leave Period",
		filters={"company": company, "from_date": ["<=", on_date], "to_date": [">=", on_date]},
		fields=["name", "from_date", "to_date"],
		order_by="from_date desc",
		limit=1,
	)
	return rows[0] if rows else None


def _preceding_period(company: str, before_date):
	rows = frappe.get_all(
		"Leave Period",
		filters={"company": company, "to_date": ["<", before_date]},
		fields=["name", "from_date", "to_date"],
		order_by="to_date desc",
		limit=1,
	)
	return rows[0] if rows else None


@frappe.whitelist()
def roll_forward_leave_periods(as_on: str | None = None, force: int | str = 0) -> dict:
	"""Carry the leave year over: open the next Leave Period, then assign the current one.

	Two separate jobs, deliberately at different moments.

	  * The next Leave Period is opened ``PERIOD_ROLL_FORWARD_LEAD_DAYS`` before the
	    latest one ends, so it exists before anybody needs to apply into it.
	  * The Leave Policy Assignment is only ever created for the period that has
	    ALREADY STARTED, for employees who held the preceding one. Carry-forward reads
	    the unused balance of the previous allocation
	    (``leave_allocation.get_carry_forwarded_leaves``), and that balance is not final
	    until the previous period is over — assigning December's successor in June would
	    carry days the employee can still spend, and hand them the same days twice.

	Idempotent: a period that exists is not recreated, and an employee who already has a
	submitted assignment overlapping the target period is skipped.

	``force`` opens the next period regardless of the lead window; it never relaxes the
	rule that an assignment waits for its period to start.
	"""
	from hrms.hr.doctype.leave_policy_assignment.leave_policy_assignment import create_assignment

	assert_doctype_permissions("Leave Period", ("create",))
	assert_doctype_permissions("Leave Policy Assignment", ("create", "submit"))

	run_date = getdate(as_on or today())
	force = cint(force)

	result = {
		"periods_created": [],
		"periods_existing": [],
		"assigned": [],
		"skipped": [],
		"failed": [],
	}

	for company in frappe.get_all("Company", pluck="name", order_by="name"):
		try:
			_open_next_period(company, run_date, force, result)
		except Exception:
			result["failed"].append({"company": company, "step": "leave_period"})
			frappe.log_error(
				frappe.get_traceback(),
				"HR Suite: could not open the next Leave Period for {0}".format(company),
			)

		try:
			_assign_current_period(company, run_date, create_assignment, result)
		except Exception:
			result["failed"].append({"company": company, "step": "assignment"})
			frappe.log_error(
				frappe.get_traceback(),
				"HR Suite: could not roll leave assignments forward for {0}".format(company),
			)

	return result


def _open_next_period(company: str, run_date, force: int, result: dict) -> None:
	latest = _latest_period(company)
	if not latest:
		result["skipped"].append({"company": company, "reason": _("No Leave Period to roll forward")})
		return

	# One period ahead is the whole job. ``force`` skips the lead-time wait, not this:
	# without it a second forced call would roll forward from the period the first call
	# created, and a third from that one, opening a new leave year on every run.
	current = _period_covering(company, run_date)
	if current and getdate(latest.to_date) > getdate(current.to_date):
		result["periods_existing"].append(latest.name)
		return

	if not force and run_date < add_days(getdate(latest.to_date), -PERIOD_ROLL_FORWARD_LEAD_DAYS):
		result["skipped"].append(
			{
				"company": company,
				"reason": _("Current Leave Period runs until {0}").format(latest.to_date),
			}
		)
		return

	next_from, next_to = _next_period_dates(latest.from_date, latest.to_date)

	existing = _period_covering(company, next_from)
	if existing:
		result["periods_existing"].append(existing.name)
		return

	doc = frappe.get_doc(
		{
			"doctype": "Leave Period",
			"company": company,
			"from_date": next_from,
			"to_date": next_to,
			"is_active": cint(next_from <= run_date <= next_to),
		}
	)
	doc.insert(ignore_permissions=True)
	result["periods_created"].append(doc.name)


def _assign_current_period(company: str, run_date, create_assignment, result: dict) -> None:
	from hr_suite.hr_suite.utils import get_employee_work_country

	current = _period_covering(company, run_date)
	if not current:
		result["skipped"].append({"company": company, "reason": _("No Leave Period covers today")})
		return

	previous = _preceding_period(company, current.from_date)
	if not previous:
		result["skipped"].append(
			{"company": company, "reason": _("No earlier Leave Period to roll forward from")}
		)
		return

	# hrms.hr.utils.get_leave_period returns EVERY active period overlapping a range and
	# callers take the first row, so a finished period left active makes that pick
	# arbitrary. A period whose to_date has passed is not active, whatever its flag says.
	if cint(frappe.db.get_value("Leave Period", previous.name, "is_active")):
		frappe.db.set_value("Leave Period", previous.name, "is_active", 0)

	employees = frappe.get_all(
		"Employee", filters={"status": "Active", "company": company}, pluck="name"
	)
	if not employees:
		return

	held_last_period = frappe.get_all(
		"Leave Policy Assignment",
		filters={
			"docstatus": 1,
			"employee": ["in", employees],
			"effective_from": ["<=", previous.to_date],
			"effective_to": [">=", previous.from_date],
		},
		fields=["employee", "leave_policy"],
	)
	if not held_last_period:
		return

	already_assigned = set(
		frappe.get_all(
			"Leave Policy Assignment",
			filters={
				"docstatus": 1,
				"employee": ["in", employees],
				"effective_from": ["<=", current.to_date],
				"effective_to": [">=", current.from_date],
			},
			pluck="employee",
		)
	)

	live_policies = set(frappe.get_all("Leave Policy", filters={"docstatus": 1}, pluck="name"))

	for row in held_last_period:
		if row.employee in already_assigned:
			continue

		policy = row.leave_policy if row.leave_policy in live_policies else ""
		if not policy:
			# The policy they held is gone. Fall back to what their country declares
			# today rather than leaving them with no allocation for the whole year.
			gender = frappe.db.get_value("Employee", row.employee, "gender")
			policy = resolve_leave_policy(get_employee_work_country(row.employee), gender)

		if not policy:
			result["skipped"].append(
				{"employee": row.employee, "reason": _("No submitted Leave Policy to assign")}
			)
			continue

		data = frappe._dict(
			{
				"assignment_based_on": "Leave Period",
				"leave_policy": policy,
				"leave_period": current.name,
				"effective_from": current.from_date,
				"effective_to": current.to_date,
				"carry_forward": 1,
			}
		)

		savepoint = "before_hr_suite_leave_roll_forward"
		frappe.db.savepoint(savepoint)
		try:
			assignment = create_assignment(row.employee, data)
			assignment.submit()
		except Exception:
			frappe.db.rollback(save_point=savepoint)
			result["failed"].append({"employee": row.employee, "step": "assignment"})
			frappe.log_error(
				frappe.get_traceback(),
				"HR Suite: roll-forward assignment failed for {0}".format(row.employee),
			)
			continue

		# Mark them assigned so a duplicated row in the source list cannot assign twice.
		already_assigned.add(row.employee)
		result["assigned"].append(
			{
				"employee": row.employee,
				"assignment": assignment.name,
				"leave_policy": policy,
				"leave_period": current.name,
			}
		)


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
		"declared_accrual": {
			code: {
				r.leave_type: (r.accrual_frequency or ACCRUAL_NONE)
				for r in _declared_rows(code)
			}
			for code in countries
		},
		"earned_leave_types": get_earned_leave_types(),
		"double_allocation": check_double_allocation_risk(),
	}
