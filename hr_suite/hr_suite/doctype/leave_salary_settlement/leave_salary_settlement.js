// Copyright (c) 2026, Enfono and contributors
// For license information, please see license.txt

const LSS = "hr_suite.hr_suite.doctype.leave_salary_settlement.leave_salary_settlement";

// The advice raised for this settlement, shown on the form, or the Create option when there is none.
// Raising it automatically after submit is left as it is; this only shows the result and covers the
// case where nothing was raised (or the advice was cancelled).
function show_payment_advice(frm) {
	frappe.call({
		method: "hr_suite.hr_suite.payment_advice.get_advice_state",
		args: { doctype: frm.doc.doctype, name: frm.doc.name },
		callback: function (r) {
			const state = r.message || {};
			if (state.advice) {
				if (frm.dashboard.wrapper.find(".hrs-advice-line").length) return;
				const label = __(state.doctype) + " " + state.advice;
				const link = state.can_open
					? frappe.utils.get_form_link(state.doctype, state.advice, true)
					: frappe.utils.escape_html(state.advice);
				frm.dashboard.add_comment(
					'<span class="hrs-advice-line">' +
						__("{0} {1}: {2}", [__(state.doctype), link, __(state.status || "Draft")]) + "</span>",
					state.status === "Paid" ? "green" : "blue",
					true
				);
				if (state.can_open) {
					frm.add_custom_button(label, function () {
						frappe.set_route("Form", state.doctype, state.advice);
					}, __("View"));
				}
				return;
			}
			if (!(frm.doc.total_payable > 0)) return;
			frm.add_custom_button(__(state.target === "HR Payment Advice" ? "HR Payment Advice" : "Payment Advice"), function () {
				frappe.call({
					method: "hr_suite.hr_suite.payment_advice.raise_for_document",
					args: { doctype: frm.doc.doctype, name: frm.doc.name },
					freeze: true,
					callback: function (res) {
						if (!res.message) return;
						frappe.show_alert({ message: __("Payment advice {0}", [res.message.advice]), indicator: "green" });
						frm.reload_doc();
					},
				});
			}, __("Create"));
		},
	});
}

frappe.ui.form.on("Leave Salary Settlement", {
	setup: function (frm) {
		frm.set_query("leave_application", function () {
			return { filters: { employee: frm.doc.employee, docstatus: 1, status: "Approved" } };
		});
	},

	refresh: function (frm) {
		if (frm.doc.docstatus !== 1 || frm.doc.status === "Cancelled") return;

		show_payment_advice(frm);

		if (frm.doc.payroll_stage && !frm.dashboard.wrapper.find(".hrs-stage-line").length) {
			frm.dashboard.add_comment(
				'<span class="hrs-stage-line">' + __("Payroll stage: {0}", [__(frm.doc.payroll_stage)]) + "</span>",
				"blue",
				true
			);
		}

		// The advice is Paid but the recovery was not booked (the automatic step could not run): do it here.
		if (frm.doc.status === "Paid" && flt(frm.doc.earning_amount) > 0 && frm.doc.payroll_stage !== "Recovery Created") {
			frm.add_custom_button(__("Create Recovery"), function () {
				frappe.call({
					method: LSS + ".create_recovery",
					args: { name: frm.doc.name },
					freeze: true,
					callback: function () { frm.reload_doc(); },
				});
			}, __("Actions"));
		}

		if (frm.doc.settlement_type === "Final Settlement") return;

		frm.add_custom_button(__("Record Rejoin"), function () {
			frappe.prompt(
				[{ fieldname: "rejoin_date", fieldtype: "Date", label: __("Rejoin Date"), reqd: 1,
				   default: frm.doc.rejoin_date || frappe.datetime.add_days(frm.doc.leave_to_date, 1) }],
				function (values) {
					frappe.call({
						method: LSS + ".record_rejoin",
						args: { name: frm.doc.name, rejoin_date: values.rejoin_date },
						freeze: true,
						callback: function () { frm.reload_doc(); },
					});
				},
				__("Return From Leave"),
				__("Record")
			);
		}, __("Actions"));

		if (flt(frm.doc.salary_days_unpaid) > 0) {
			frm.dashboard.add_comment(
				__("{0} salary day(s) are still due. Create a further settlement once they are earned.", [frm.doc.salary_days_unpaid]),
				"orange", true
			);
		}
	},
});
