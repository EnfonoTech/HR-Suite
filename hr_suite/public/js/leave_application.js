// HR Suite — Leave Application: the employee's leave position since joining, and start a Leave Salary
// Settlement from an approved leave.
frappe.ui.form.on("Leave Application", {
	employee: function (frm) {
		hr_suite_leave_summary(frm);
	},
	refresh: function (frm) {
		hr_suite_leave_summary(frm);
		if (frm.doc.docstatus !== 1 || frm.doc.status !== "Approved") return;
		if (frappe.user.has_role("HR Manager")) {
			frm.add_custom_button(__("Change Dates"), () => hr_suite_change_dates(frm), __("Actions"));
		}
		if (!frappe.model.can_create("Leave Salary Settlement")) return;

		frm.add_custom_button(
			__("Leave Salary Settlement"),
			function () {
				frappe.call({
					method: "hr_suite.hr_suite.doctype.leave_salary_settlement.leave_salary_settlement.make_from_leave_application",
					args: { leave_application: frm.doc.name },
					callback: function (r) {
						if (!r.message) return;
						const doc = frappe.model.sync(r.message)[0];
						frappe.set_route("Form", doc.doctype, doc.name);
					},
				});
			},
			__("Create")
		);
	},
});

// ─── Change the dates of an approved leave not yet settled (SFT reply, section 11) ──────────────────────
// The server cancels the approved leave and creates its amendment with the new dates, back for approval.
function hr_suite_change_dates(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Change Leave Dates"),
		fields: [
			{
				fieldtype: "HTML",
				options: `<p class="text-muted">${__(
					"{0} will be cancelled and a copy with the new dates goes back to {1} for approval. A leave whose salary is settled cannot be changed here.",
					[frm.doc.name, frappe.utils.escape_html(frm.doc.leave_approver || __("the approver"))]
				)}</p>`,
			},
			{ fieldname: "from_date", fieldtype: "Date", label: __("From Date"), reqd: 1, default: frm.doc.from_date },
			{ fieldname: "to_date", fieldtype: "Date", label: __("To Date"), reqd: 1, default: frm.doc.to_date },
			{ fieldname: "half_day", fieldtype: "Check", label: __("Half Day"), default: frm.doc.half_day },
			{
				fieldname: "half_day_date",
				fieldtype: "Date",
				label: __("Half Day Date"),
				depends_on: "half_day",
				default: frm.doc.half_day_date,
			},
			{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason For The Change") },
		],
		primary_action_label: __("Change And Send For Approval"),
		primary_action(values) {
			frappe.call({
				method: "hr_suite.hr_suite.leave_change.change_approved_leave_dates",
				args: Object.assign({ application: frm.doc.name }, values),
				freeze: true,
				freeze_message: __("Changing the leave dates..."),
				callback(r) {
					if (!r.message) return;
					d.hide();
					frappe.show_alert({ message: __("{0} sent for approval", [r.message]), indicator: "green" });
					frappe.set_route("Form", "Leave Application", r.message);
				},
			});
		},
	});
	d.show();
}

// ─── Leave position: employee, service, leave per type since joining, history, leave-salary days ──────
function hr_suite_leave_summary(frm) {
	if (!frm.doc.employee) return;
	frappe.call({
		method: "hr_suite.hr_suite.leave_summary.get_leave_summary",
		args: { employee: frm.doc.employee },
		callback: function (r) {
			if (!r.message || frm.doc.employee !== r.message.employee.name) return;
			$(frm.dashboard.wrapper).find(".hrs-leave-summary").closest(".form-dashboard-section").remove();
			frm.dashboard.add_section(hr_suite_leave_summary_html(r.message), __("Leave Position Since Joining"));
			frm.dashboard.show();
		},
	});
}

function hr_suite_leave_summary_html(data) {
	const esc = (v) => frappe.utils.escape_html(v == null ? "" : String(v));
	const num = (v) => (v == null ? "-" : format_number(v, null, 2));
	const date = (v) => (v ? frappe.datetime.str_to_user(v) : "-");
	const emp = data.employee;
	const svc = data.service || {};
	const ls = data.leave_salary;

	const info = [
		[__("Employee"), `${esc(emp.name)}: ${esc(emp.employee_name)}`],
		[__("Designation"), esc(emp.designation || "-")],
		[__("Department"), esc(emp.department || "-")],
		[__("Date of Joining"), date(emp.date_of_joining)],
		[__("Service"), svc.total_days ? __("{0} years {1} months {2} days ({3} days)", [svc.years, svc.months, svc.days, svc.total_days]) : "-"],
		[__("Leave Salary Days"), __("Earned {0}, settled {1}, balance {2}", [num(ls.earned_days), num(ls.settled_days), `<b>${num(ls.balance_days)}</b>`])],
	].map(([k, v]) => `<div class="col-sm-4" style="margin-bottom:8px"><div class="text-muted small">${k}</div><div>${v}</div></div>`).join("");

	const table = (head, rows) => rows.length
		? `<table class="table table-bordered table-sm" style="margin-top:8px"><thead><tr>${head.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table>`
		: `<p class="text-muted small">${__("None")}</p>`;

	const types = table(
		[__("Leave Type"), __("Allocated Since Joining"), __("Taken Since Joining"), __("Pending Approval"), __("Balance Today")],
		(data.leave_types || []).map((t) => `<tr><td>${esc(t.leave_type)}</td><td>${num(t.allocated)}</td><td>${num(t.taken)}</td><td>${num(t.pending)}</td><td><b>${num(t.balance)}</b></td></tr>`)
	);
	const history = table(
		[__("Application"), __("Leave Type"), __("From"), __("To"), __("Days"), __("Status")],
		(data.history || []).map((h) => `<tr><td><a href="/app/leave-application/${encodeURIComponent(h.name)}">${esc(h.name)}</a></td><td>${esc(h.leave_type)}</td><td>${date(h.from_date)}</td><td>${date(h.to_date)}</td><td>${num(h.total_leave_days)}</td><td>${esc(__(h.status))}</td></tr>`)
	);
	const settlements = table(
		[__("Settlement"), __("Leave"), __("Salary Days Paid"), __("Leave Salary"), __("Air Ticket"), __("Total"), __("Rejoined"), __("Status")],
		(ls.settlements || []).map((s) => `<tr><td><a href="/app/leave-salary-settlement/${encodeURIComponent(s.name)}">${esc(s.name)}</a></td><td>${date(s.leave_from_date)} - ${date(s.leave_to_date)}</td><td>${num(s.salary_days_paid)}</td><td>${format_currency(s.leave_salary_amount)}</td><td>${format_currency(s.ticket_amount)}</td><td>${format_currency(s.total_payable)}</td><td>${date(s.rejoin_date)}</td><td>${esc(__(s.status))}</td></tr>`)
	);

	return `<div class="hrs-leave-summary">
		<div class="row">${info}</div>
		<h6 style="margin-top:12px">${__("Leave by Type")}</h6>${types}
		<h6 style="margin-top:12px">${__("Recent Leave Applications")}</h6>${history}
		<h6 style="margin-top:12px">${__("Leave Salary Settlements")}</h6>${settlements}
	</div>`;
}
