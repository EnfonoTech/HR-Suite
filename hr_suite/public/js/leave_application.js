// HR Suite — Leave Application: start a Leave Salary Settlement from an approved leave.
frappe.ui.form.on("Leave Application", {
	refresh: function (frm) {
		if (frm.doc.docstatus !== 1 || frm.doc.status !== "Approved") return;
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
