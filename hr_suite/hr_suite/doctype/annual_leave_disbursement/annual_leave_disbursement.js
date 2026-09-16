// Copyright (c) 2026, Enfono and contributors
// For license information, please see license.txt

const ALD_METHOD = "hr_suite.hr_suite.doctype.annual_leave_disbursement.annual_leave_disbursement";

frappe.ui.form.on("Annual Leave Disbursement", {
	setup: function (frm) {
		// Only this employee's leave, and only leave that was actually approved — a
		// rejected application must not be able to set the dates money is paid against.
		frm.set_query("leave_application", function () {
			return {
				filters: {
					employee: frm.doc.employee,
					docstatus: 1,
					status: "Approved",
				},
			};
		});
	},

	employee: function (frm) {
		if (!frm.doc.employee) return;
		frappe.db.get_value("Employee", frm.doc.employee, ["employee_name", "company", "department"], (r) => {
			if (r) {
				frm.set_value("employee_name", r.employee_name);
				frm.set_value("company", r.company);
				frm.set_value("department", r.department);
			}
		});
		frm.trigger("load_leave_balance");
	},

	leave_type: function (frm) {
		frm.trigger("load_leave_balance");
	},

	leave_application: function (frm) {
		if (!frm.doc.leave_application) return;
		frappe.call({
			method: ALD_METHOD + ".get_leave_application_details",
			args: { leave_application: frm.doc.leave_application },
			callback: function (r) {
				if (!r.message) return;
				frm.set_value("leave_type", r.message.leave_type);
				frm.set_value("leave_from_date", r.message.from_date);
				frm.set_value("leave_to_date", r.message.to_date);
				frm.set_value("leave_days_to_pay", r.message.total_leave_days);
			},
		});
	},

	load_leave_balance: function (frm) {
		if (!frm.doc.employee || !frm.doc.leave_type) return;
		frappe.call({
			method: ALD_METHOD + ".get_leave_balance",
			args: {
				employee: frm.doc.employee,
				leave_type: frm.doc.leave_type,
				on_date: frm.doc.leave_from_date,
			},
			callback: function (r) {
				if (!r.message) return;
				frm.set_value("leave_allocation", r.message.allocation);
				frm.set_value("leave_days_entitled", r.message.entitled);
				frm.set_value("leave_days_taken", r.message.taken);
				frm.set_value("leave_days_balance", r.message.balance);
				if (!r.message.allocation) {
					frm.dashboard.add_comment(
						__("No Leave Allocation for {0} covers this date. Allocate the leave before disbursing it.",
							[frm.doc.leave_type]),
						"red", true
					);
				}
			},
		});
	},

	leave_from_date: function (frm) {
		frm.trigger("compute_days");
		frm.trigger("load_leave_balance");
	},

	leave_to_date: function (frm) {
		frm.trigger("compute_days");
	},

	compute_days: function (frm) {
		if (!frm.doc.leave_from_date || !frm.doc.leave_to_date) return;
		let diff = frappe.datetime.get_diff(frm.doc.leave_to_date, frm.doc.leave_from_date) + 1;
		if (diff > 0 && !frm.doc.leave_application) {
			frm.set_value("leave_days_to_pay", diff);
		}
	},

	leave_days_to_pay: function (frm) {
		if (frm.doc.leave_days_balance && frm.doc.leave_days_to_pay > frm.doc.leave_days_balance) {
			frappe.msgprint({
				title: __("Exceeds Balance"),
				message: __("Days to disburse ({0}) exceed the allocation balance ({1}). Saving will be refused.",
					[frm.doc.leave_days_to_pay, frm.doc.leave_days_balance]),
				indicator: "orange",
			});
		}
		frm.trigger("preview_pay");
	},

	preview_pay: function (frm) {
		// Preview only. The server prices the leave again on save and that figure wins.
		if (!frm.doc.employee || !frm.doc.leave_days_to_pay) return;
		frappe.call({
			method: ALD_METHOD + ".get_leave_salary_preview",
			args: { employee: frm.doc.employee, days: frm.doc.leave_days_to_pay },
			callback: function (r) {
				if (!r.message) return;
				frm.dashboard.add_comment(
					__("{0} — {1} day(s) at {2} a day",
						[r.message.terms.basis, r.message.days, format_currency(r.message.daily_rate)]),
					"blue", true
				);
			},
		});
	},

	refresh: function (frm) {
		frm.set_intro(
			__("Leave salary is an advance of the salary for the same days. On submit this posts a " +
			   "Journal Entry for the total and books one deduction per payroll month, so the days " +
			   "are not paid twice. The annual ticket is never recovered."),
			"blue"
		);

		if (frm.doc.linked_payroll_entry) {
			frm.add_custom_button(__("Journal Entry"), function () {
				frappe.set_route("Form", "Journal Entry", frm.doc.linked_payroll_entry);
			}, __("View"));
		}

		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Payroll Recovery"), function () {
				frappe.set_route("List", "Additional Salary", {
					ref_doctype: frm.doc.doctype,
					ref_docname: frm.doc.name,
				});
			}, __("View"));
		}

		if (frm.doc.docstatus === 1 && frm.doc.status !== "Paid") {
			frm.add_custom_button(__("Mark as Paid"), function () {
				frappe.confirm(
					__("Confirm leave disbursement payment of {0}?", [format_currency(frm.doc.total_leave_pay)]),
					function () {
						frappe.db.set_value("Annual Leave Disbursement", frm.doc.name, "status", "Paid")
							.then(() => frm.reload_doc());
					}
				);
			}, __("Actions"));
		}

		if (frm.doc.leave_salary_basis) {
			frm.dashboard.add_comment(frm.doc.leave_salary_basis, "green", true);
		}

		add_payment_advice_button(frm);
	},
});

// Ask finance to pay this document. Deliberately a button and not an on_submit hook:
// raising (and submitting) a second submittable document inside another document's
// submit transaction is how a payroll run died here once — anything the advice refuses
// would roll the source document back with it.
function add_payment_advice_button(frm) {
	if (frm.doc.docstatus !== 1) return;

	frm.add_custom_button(__("Raise Payment Advice"), function () {
		frappe.call({
			method: "hr_suite.hr_suite.payment_advice.raise_for_document",
			args: { doctype: frm.doc.doctype, name: frm.doc.name },
			freeze: true,
			freeze_message: __("Raising payment advice..."),
			callback(r) {
				if (!r.message) return;
				frappe.show_alert({
					message: r.message.created
						? __("Payment Advice {0} raised.", [r.message.advice])
						: __("Payment Advice {0} was already raised for this document.", [r.message.advice]),
					indicator: "green",
				});
				frappe.set_route("Form", "HR Payment Advice", r.message.advice);
			},
		});
	}, __("Actions"));
}

