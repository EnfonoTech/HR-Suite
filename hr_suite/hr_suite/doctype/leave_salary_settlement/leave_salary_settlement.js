// Copyright (c) 2026, Enfono and contributors
// For license information, please see license.txt

const LSS = "hr_suite.hr_suite.doctype.leave_salary_settlement.leave_salary_settlement";

frappe.ui.form.on("Leave Salary Settlement", {
	setup: function (frm) {
		frm.set_query("leave_application", function () {
			return { filters: { employee: frm.doc.employee, docstatus: 1, status: "Approved" } };
		});
	},

	refresh: function (frm) {
		if (frm.doc.docstatus !== 1 || frm.doc.status === "Cancelled") return;

		if (frm.doc.total_payable > 0 && !frm.doc.payment_advice) {
			frm.add_custom_button(__("Payment Advice"), function () {
				frappe.call({
					method: "hr_suite.hr_suite.payment_advice.raise_for_document",
					args: { doctype: frm.doc.doctype, name: frm.doc.name },
					freeze: true,
					callback: function (r) {
						if (!r.message) return;
						frappe.show_alert({ message: __("Payment advice {0}", [r.message.advice]), indicator: "green" });
						frm.reload_doc();
					},
				});
			}, __("Create"));
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
