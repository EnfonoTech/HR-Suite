"""
tasks.py — Scheduled Tasks for daily alerts.
"""
import frappe
from frappe.utils import today, add_days, flt, get_first_day, get_last_day, getdate


DEFAULT_ALERT_MILESTONES = (30, 14, 7, 1, 0)


def _get_hr_suite_settings():
	return frappe.get_single("Hr Suite Settings")


def _email_alerts_enabled():
	settings = _get_hr_suite_settings()
	return bool(settings.send_email_alerts)


def _get_alert_milestones(primary_day: int | None = None) -> set[int]:
	milestones = set(DEFAULT_ALERT_MILESTONES)
	if primary_day is not None:
		milestones.add(int(primary_day))
	return {day for day in milestones if day >= 0}


def _should_send_days_left_alert(days_left: int, primary_day: int | None = None) -> bool:
	return int(days_left) in _get_alert_milestones(primary_day)


def _has_existing_alert(user: str, subject: str, doctype: str, docname=None) -> bool:
	filters = {
		"for_user": user,
		"subject": subject,
		"document_type": doctype,
		"type": "Alert",
	}
	if docname:
		filters["document_name"] = docname
	return bool(frappe.db.exists("Notification Log", filters))


def _get_pending_alert_recipients(recipients, subject: str, doctype: str, docname=None) -> list[str]:
	return [
		user for user in recipients
		if not _has_existing_alert(user, subject, doctype, docname)
	]


def send_iqama_expiry_alerts():
	"""Alert for Iqama expiry 90 and 30 days before."""
	settings = _get_hr_suite_settings()
	alert_days = settings.iqama_expiry_alert_days or 90

	records = frappe.get_all(
		"Work Permit Iqama",
		filters={
			"iqama_expiry_date": ["between", [today(), add_days(today(), alert_days)]],
			"docstatus": 1,
		},
		fields=["name", "employee", "employee_name", "iqama_expiry_date"],
	)

	for rec in records:
		days_left = (getdate(rec.iqama_expiry_date) - getdate(today())).days
		if not _should_send_days_left_alert(days_left, alert_days):
			continue
		_send_alert(
			subject=f"Alert: Iqama expiry for {rec.employee_name} in {days_left} days",
			message=f"Employee {rec.employee_name} ({rec.employee}) Iqama expires on {rec.iqama_expiry_date}.",
			doctype="Work Permit Iqama",
			docname=rec.name,
		)


def send_contract_expiry_alerts():
	"""Alert for fixed-term contract expiry within 60 days."""
	settings = _get_hr_suite_settings()
	alert_days = settings.contract_expiry_alert_days or 60

	records = frappe.get_all(
		"Saudi Employment Contract",
		filters={
			"contract_type": "Fixed Term",
			"end_date": ["between", [today(), add_days(today(), alert_days)]],
			"contract_status": "Active",
		},
		fields=["name", "employee", "employee_name", "end_date"],
	)

	for rec in records:
		days_left = (getdate(rec.end_date) - getdate(today())).days
		if not _should_send_days_left_alert(days_left, alert_days):
			continue
		_send_alert(
			subject=f"Alert: Contract expiry for {rec.employee_name} in {days_left} days",
			message=f"Employee {rec.employee_name} ({rec.employee}) contract expires on {rec.end_date}.",
			doctype="Saudi Employment Contract",
			docname=rec.name,
		)


def send_work_permit_expiry_alerts():
	"""Alert for work permit expiry within 90 days."""
	settings = _get_hr_suite_settings()
	alert_days = settings.work_permit_expiry_alert_days or 90

	records = frappe.get_all(
		"Work Permit Iqama",
		filters={
			"work_permit_expiry_date": ["between", [today(), add_days(today(), alert_days)]],
			"docstatus": 1,
		},
		fields=["name", "employee", "employee_name", "work_permit_expiry_date"],
	)

	for rec in records:
		days_left = (getdate(rec.work_permit_expiry_date) - getdate(today())).days
		if not _should_send_days_left_alert(days_left, alert_days):
			continue
		_send_alert(
			subject=f"Alert: Work permit expiry for {rec.employee_name} in {days_left} days",
			message=f"Employee {rec.employee_name} ({rec.employee}) work permit expires on {rec.work_permit_expiry_date}.",
			doctype="Work Permit Iqama",
			docname=rec.name,
		)


def send_gosi_due_alerts():
	"""Monthly reminder for unpaid GOSI contributions of the previous payroll month."""
	today_date = getdate(today())
	first_of_month = today_date.replace(day=1)
	previous_month_date = add_days(first_of_month, -1)
	period_month = previous_month_date.strftime("%B")
	period_year = previous_month_date.year

	pending_records = frappe.get_all(
		"GOSI Contribution",
		filters={
			"month": period_month,
			"year": period_year,
			"payment_status": ["!=", "Paid"],
		},
		fields=["name", "employee_name", "company", "total_contribution", "payment_status"],
		order_by="company asc, employee_name asc",
	)

	if not pending_records:
		return

	total_amount = sum((record.total_contribution or 0) for record in pending_records)
	companies = sorted({record.company for record in pending_records if record.company})
	preview = ", ".join(record.employee_name for record in pending_records[:5] if record.employee_name)
	remaining_count = max(0, len(pending_records) - 5)
	if remaining_count:
		preview = f"{preview}, +{remaining_count}" if preview else f"+{remaining_count}"

	message = (
		f"There are {len(pending_records)} unpaid GOSI contribution records for {period_month} {period_year}.\n"
		f"Total amount due: {total_amount:,.2f} SAR.\n"
	)
	if companies:
		message += f"Companies involved: {', '.join(companies)}.\n"
	if preview:
		message += f"Example records: {preview}.\n"
	message += "Please review pending GOSI records and update payment status and reference number."

	_send_alert(
		subject=f"Monthly GOSI Alert: {len(pending_records)} pending records for {period_month} {period_year}",
		message=message,
		doctype="GOSI Contribution",
		docname=pending_records[0].name,
	)


def _send_alert(subject, message, doctype, docname=None):
	"""Send email alert and internal notification to HR Manager."""
	hr_managers = frappe.get_all(
		"Has Role",
		filters={"role": "HR Manager", "parenttype": "User"},
		fields=["parent"],
	)
	recipients = [r.parent for r in hr_managers if r.parent != "Guest"]
	recipients = _get_pending_alert_recipients(recipients, subject, doctype, docname)
	if not recipients:
		return

	site_url = frappe.utils.get_url()
	if docname:
		doc_url = f"{site_url}/app/{frappe.scrub(doctype)}/{docname}"
	else:
		doc_url = f"{site_url}/app/{frappe.scrub(doctype)}"

	html_message = f"""
	<div dir="rtl" style="font-family:Arial,Tahoma,sans-serif;font-size:13px;color:#222;padding:20px;">
		<div style="background:#1a5276;color:white;padding:12px 20px;border-radius:5px;margin-bottom:15px;">
			<strong>Saudi HR System — Hr Suite</strong>
		</div>
		<p>{message}</p>
		<p style="margin-top:20px;">
			<a href="{doc_url}" style="background:#1a5276;color:white;padding:8px 18px;
			text-decoration:none;border-radius:4px;font-size:13px;">
				View Document →
			</a>
		</p>
		<hr style="border:1px solid #eee;margin-top:25px;">
		<p style="font-size:11px;color:#888;">This is an automated email from the Saudi HR System</p>
	</div>
	"""

	if recipients and _email_alerts_enabled():
		frappe.sendmail(
			recipients=recipients,
			subject=subject,
			message=html_message,
			reference_doctype=doctype,
			reference_name=docname,
		)

	# Internal system notification
	for user in recipients:
		frappe.publish_realtime(
			"eval_js",
			f"frappe.show_alert({{message: '{subject.replace(chr(39), '')}', indicator: 'orange'}})",
			user=user,
		)
		frappe.get_doc({
			"doctype": "Notification Log",
			"subject": subject,
			"email_content": message,
			"document_type": doctype,
			"document_name": docname,
			"for_user": user,
			"type": "Alert",
		}).insert()


def send_sick_leave_threshold_alerts():
	"""Alert when an employee approaches the 90-day sick leave threshold."""
	from frappe.utils import getdate
	import datetime

	year = getdate(frappe.utils.today()).year
	# Find employees with 75-90 sick days this year
	results = frappe.db.sql("""
		SELECT employee, employee_name, SUM(total_days) as total_sick
		FROM `tabSick Leave`
		WHERE YEAR(from_date) = %s AND docstatus = 1
		GROUP BY employee
		HAVING total_sick BETWEEN 75 AND 120
	""", (year,), as_dict=True)

	for rec in results:
		# Find the most recent sick leave record for the employee to use as doc link
		latest_doc = frappe.db.sql(
			"""SELECT name FROM `tabSick Leave`
			   WHERE employee=%s AND YEAR(from_date)=%s AND docstatus=1
			   ORDER BY from_date DESC LIMIT 1""",
			(rec.employee, year),
			as_list=True,
		)
		_send_alert(
			subject=f"Alert: {rec.employee_name} is approaching the maximum sick leave limit ({int(rec.total_sick)} days)",
			message=f"Employee {rec.employee_name} has used {int(rec.total_sick)} sick days this year. Maximum is 120 days (Article 117).",
			doctype="Sick Leave",
			docname=latest_doc[0][0] if latest_doc else "",
		)


def send_probation_end_alerts():
	"""Alert for probation period expiry 14 days in advance (Article 53 of Saudi Labor Law).
	Alert HR Manager + direct manager when probation ends within 14 days.
	"""
	two_weeks_ahead = add_days(today(), 14)
	records = frappe.get_all(
		"Saudi Employment Contract",
		filters={
			"probation_end_date": ["between", [today(), two_weeks_ahead]],
			"contract_status": "Active",
		},
		fields=["name", "employee", "employee_name", "probation_end_date", "probation_period_days"],
	)

	for rec in records:
		days_left = (getdate(rec.probation_end_date) - getdate(today())).days
		if not _should_send_days_left_alert(days_left, 14):
			continue
		_send_alert(
			subject=(
				f"Probation Alert: {rec.employee_name} — ends in {days_left} days"
			),
			message=(
				f"Employee {rec.employee_name} ({rec.employee}) probation period ends on "
				f"{rec.probation_end_date} (in {days_left} days).\n\n"
				"Please decide whether to confirm or terminate employment before the probation period ends "
				"in accordance with Saudi Labor Law Article 53."
			),
			doctype="Saudi Employment Contract",
			docname=rec.name,
		)


def _doctype_exists(doctype):
	return bool(frappe.db.exists("DocType", doctype))


def _send_due_alerts(doctype, date_field, title_field, subject_label, closed_statuses=None, days_ahead=7, status_field="status"):
	if not _doctype_exists(doctype):
		return

	closed_statuses = closed_statuses or []
	filters = {
		date_field: ["<=", add_days(today(), days_ahead)],
	}
	if closed_statuses:
		filters[status_field] = ["not in", closed_statuses]

	records = frappe.get_all(
		doctype,
		filters=filters,
		fields=["name", title_field, date_field, status_field],
		order_by=f"{date_field} asc",
		limit_page_length=50,
	)
	for rec in records:
		due_date = rec.get(date_field)
		if not due_date:
			continue
		days_left = (getdate(due_date) - getdate(today())).days
		if days_left > days_ahead:
			continue
		title = rec.get(title_field) or rec.name
		_send_alert(
			subject=f"{subject_label}: {title} in {days_left} days",
			message=(
				f"There is a compliance item requiring follow-up: {title}. "
				f"Due date: {due_date}. Current status: {rec.get(status_field) or '-'}."
			),
			doctype=doctype,
			docname=rec.name,
		)


def send_ministry_filing_due_alerts():
	_send_due_alerts(
		"Ministry Filing Tracker",
		"due_date",
		"filing_title",
		"Ministry Filing Deadline Alert",
		closed_statuses=["Accepted", "Cancelled"],
	)


def send_final_settlement_sla_alerts():
	_send_due_alerts(
		"Final Settlement SLA",
		"settlement_due_date",
		"employee_name",
		"Final Settlement Deadline Alert",
		closed_statuses=["Settled", "Cancelled"],
		days_ahead=5,
	)


def send_employee_document_custody_alerts():
	_send_due_alerts(
		"Employee Document Custody Log",
		"return_due_date",
		"employee_name",
		"Employee Document Return Alert",
		closed_statuses=["Returned", "Not Held"],
		days_ahead=3,
		status_field="custody_status",
	)


def send_inspection_fine_sla_alerts():
	_send_due_alerts(
		"Inspection Fine SLA",
		"payment_due_date",
		"fine_reference",
		"Inspection Fine Payment Deadline Alert",
		closed_statuses=["Paid", "Waived", "Closed"],
		days_ahead=10,
	)


def send_wps_correction_due_alerts():
	_send_due_alerts(
		"WPS Submission",
		"correction_due_date",
		"pay_period",
		"WPS Correction Deadline Alert",
		closed_statuses=["Submitted", "Accepted", "Cancelled"],
		days_ahead=5,
	)


def send_work_regulation_review_alerts():
	_send_due_alerts(
		"Work Regulation",
		"next_review_date",
		"regulation_title",
		"Work Regulation Review Alert",
		closed_statuses=["Archived"],
		days_ahead=30,
	)


def send_expat_authorization_due_alerts():
	_send_due_alerts(
		"Expat Work Authorization Control",
		"due_date",
		"employee_name",
		"Non-Saudi Worker Action Deadline Alert",
		closed_statuses=["Approved", "Closed"],
		days_ahead=14,
	)


def send_training_disclosure_due_alerts():
	_send_due_alerts(
		"Training Disclosure Register",
		"disclosure_due_date",
		"company",
		"Training Disclosure Deadline Alert",
		closed_statuses=["Accepted", "Closed"],
		days_ahead=30,
	)


def allocate_monthly_leave():
	"""Auto-create HRMS Leave Allocations for the current month for every active employee.

	Reads leave types and annual days from Country Config; prorates to monthly (annual / 12).
	Skips employees whose country config has no leave_types configured.
	Skips if an allocation already exists for the same employee + leave_type + period.
	Runs on the 1st of each month via scheduler_events["monthly"].
	"""
	if not frappe.db.get_single_value("Hr Suite Settings", "monthly_leave_allocation_enabled"):
		return

	from hr_suite.hr_suite.utils import get_employee_work_country, get_country_config

	run_date = getdate(today())
	from_date = str(get_first_day(run_date))
	to_date = str(get_last_day(run_date))

	employees = frappe.get_all(
		"Employee",
		filters={"status": "Active"},
		fields=["name", "employee_name", "company", "department"],
	)

	created = 0
	for emp in employees:
		country = get_employee_work_country(emp.name)
		cfg = get_country_config(country)
		if not cfg or not cfg.leave_types:
			continue

		for lt in cfg.leave_types:
			leave_type_name = (lt.leave_type_name or "").strip()
			if not leave_type_name:
				continue
			# Verify the Leave Type exists in HRMS
			if not frappe.db.exists("Leave Type", leave_type_name):
				continue

			annual_days = flt(lt.get("days_per_year") or lt.get("days_below_threshold") or 0)
			if annual_days <= 0:
				continue

			monthly_days = round(annual_days / 12, 4)

			# Skip if allocation for this period already exists
			if frappe.db.exists("Leave Allocation", {
				"employee": emp.name,
				"leave_type": leave_type_name,
				"from_date": from_date,
				"to_date": to_date,
				"docstatus": ["<", 2],
			}):
				continue

			try:
				doc = frappe.new_doc("Leave Allocation")
				doc.employee = emp.name
				doc.employee_name = emp.employee_name
				doc.department = emp.department
				doc.company = emp.company
				doc.leave_type = leave_type_name
				doc.from_date = from_date
				doc.to_date = to_date
				doc.new_leaves_allocated = monthly_days
				doc.carry_forward = 0
				doc.insert(ignore_permissions=True)
				doc.submit()
				created += 1
			except Exception:
				frappe.log_error(
					f"Monthly leave allocation failed for {emp.name} / {leave_type_name}",
					"HR Suite Monthly Leave Allocation",
				)

	if created:
		frappe.logger().info(f"HR Suite: created {created} monthly Leave Allocation records for {from_date} – {to_date}")
