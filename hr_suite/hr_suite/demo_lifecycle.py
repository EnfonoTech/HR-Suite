from __future__ import annotations

import frappe
from frappe.utils import add_days, nowdate


def _first_company() -> str:
	companies = frappe.get_all("Company", pluck="name", limit_page_length=1)
	if not companies:
		frappe.throw("Create a Company before seeding Hr Suite lifecycle demo data.")
	return companies[0]


def _first_gender() -> str:
	for candidate in ("Prefer not to say", "Male", "Female"):
		if frappe.db.exists("Gender", candidate):
			return candidate
	genders = frappe.get_all("Gender", pluck="name", limit_page_length=1)
	if genders:
		return genders[0]
	frappe.throw("Create at least one Gender before seeding Employee data.")


def _ensure_user(email: str, first_name: str, roles: tuple[str, ...]) -> str:
	if not frappe.db.exists("User", email):
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": first_name,
				"enabled": 1,
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)
	else:
		user = frappe.get_doc("User", email)
		user.enabled = 1
		user.save(ignore_permissions=True)

	for role in roles:
		user.add_roles(role)
	return email


def _ensure_employee(email: str, first_name: str, company: str, gender: str, reports_to: str | None = None) -> str:
	existing = frappe.db.get_value("Employee", {"user_id": email}, "name")
	if existing:
		employee = frappe.get_doc("Employee", existing)
	else:
		employee = frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": first_name,
				"employee_name": first_name,
				"gender": gender,
				"date_of_birth": "1990-01-01",
				"date_of_joining": "2026-01-01",
				"company": company,
				"user_id": email,
				"status": "Active",
			}
		)
	if reports_to:
		employee.reports_to = reports_to
	employee.status = "Active"
	employee.save(ignore_permissions=True)
	return employee.name


def _ensure_contract(employee: str, company: str):
	existing = frappe.db.get_value(
		"Saudi Employment Contract",
		{"employee": employee, "company": company, "start_date": "2026-01-01", "docstatus": ("<", 2)},
		"name",
	)
	if existing:
		return existing

	return frappe.get_doc(
		{
			"doctype": "Saudi Employment Contract",
			"employee": employee,
			"company": company,
			"contract_type": "Fixed Term",
			"contract_status": "Active",
			"start_date": "2026-01-01",
			"end_date": "2026-12-31",
			"basic_salary": 8000,
			"housing_allowance": 2000,
			"transport_allowance": 750,
			"other_allowances": 250,
		}
	).insert(ignore_permissions=True).name


def _ensure_warning(employee: str, company: str):
	existing = frappe.db.get_value(
		"Employee Warning Notice",
		{"employee": employee, "warning_date": "2026-02-10", "docstatus": ("<", 2)},
		"name",
	)
	if existing:
		return existing

	return frappe.get_doc(
		{
			"doctype": "Employee Warning Notice",
			"employee": employee,
			"company": company,
			"warning_date": "2026-02-10",
			"warning_level": "First Written Warning",
			"issue_reason": "Repeated late arrival during probation review.",
			"corrective_action": "Manager follow-up and weekly attendance review.",
			"due_date": "2026-02-17",
		}
	).insert(ignore_permissions=True).name


def _ensure_leave(employee: str, company: str):
	existing = frappe.db.get_value(
		"Saudi Annual Leave",
		{"employee": employee, "leave_start_date": "2026-03-01", "docstatus": ("<", 2)},
		"name",
	)
	if existing:
		return existing

	doc = frappe.get_doc(
		{
			"doctype": "Saudi Annual Leave",
			"employee": employee,
			"company": company,
			"leave_start_date": "2026-03-01",
			"leave_end_date": "2026-03-03",
			"description": "Demo lifecycle annual leave request.",
		}
	)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = False
	from frappe.workflow.doctype.workflow_action import workflow_action

	original_enqueue = workflow_action.enqueue
	workflow_action.enqueue = lambda *args, **kwargs: None
	try:
		return doc.insert(ignore_permissions=True).name
	finally:
		workflow_action.enqueue = original_enqueue


def _ensure_payroll(employee: str, company: str):
	existing = frappe.db.get_value(
		"Saudi Monthly Payroll",
		{"company": company, "month": "March", "year": 2026, "notes": "Hr Suite demo lifecycle payroll run.", "docstatus": ("<", 2)},
		"name",
	)
	if existing:
		return existing

	payroll = frappe.get_doc(
		{
			"doctype": "Saudi Monthly Payroll",
			"company": company,
			"month": "March",
			"year": 2026,
			"posting_date": "2026-03-31",
			"employees": [
				{
					"employee": employee,
					"basic_salary": 8000,
					"housing_allowance": 2000,
					"transport_allowance": 750,
					"other_allowances": 250,
					"other_deductions": 150,
				}
			],
			"notes": "Hr Suite demo lifecycle payroll run.",
		}
	).insert(ignore_permissions=True)
	payroll.flags.ignore_permissions = True
	payroll.submit()
	return payroll.name


def seed_employee_lifecycle_demo():
	frappe.set_user("Administrator")
	company = _first_company()
	gender = _first_gender()
	manager_email = _ensure_user("saudi.lifecycle.manager@example.com", "Saudi Lifecycle Manager", ("Department Approver",))
	employee_email = _ensure_user("saudi.lifecycle.employee@example.com", "Saudi Lifecycle Employee", ("Employee Self Service",))

	manager = _ensure_employee(manager_email, "Saudi Lifecycle Manager", company, gender)
	employee = _ensure_employee(employee_email, "Saudi Lifecycle Employee", company, gender, reports_to=manager)

	contract = _ensure_contract(employee, company)
	warning = _ensure_warning(employee, company)
	leave = _ensure_leave(employee, company)
	payroll = _ensure_payroll(employee, company)

	settings = frappe.get_single("Hr Suite Settings")
	settings.mobile_attendance_base_url = frappe.utils.get_url().rstrip("/")
	settings.save(ignore_permissions=True)

	frappe.db.commit()
	return {
		"company": company,
		"manager": manager,
		"employee": employee,
		"contract": contract,
		"warning": warning,
		"leave": leave,
		"payroll": payroll,
		"seeded_on": nowdate(),
		"next_review_date": add_days(nowdate(), 30),
	}
