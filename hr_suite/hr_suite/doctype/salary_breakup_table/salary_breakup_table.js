frappe.ui.form.on("Salary Breakup Table", {
	refresh: function (frm) {
		frm.add_custom_button(__("Import Breakup Table"), function () {
			hr_suite_breakup.import_table(frm);
		});
	},
});

frappe.provide("hr_suite_breakup");

hr_suite_breakup.import_table = function (frm) {
	if (!frm.doc.breakup_workbook) {
		frappe.msgprint(__("Attach a Salary Breakup Workbook first."));
		return;
	}

	frappe.confirm(
		__("This will replace the current Breakup Rows table with the rows from the attached workbook. Continue?"),
		function () {
			frappe.call({
				method: "hr_suite.hr_suite.doctype.salary_breakup_table.salary_breakup_table.import_breakup_table",
				args: { file_url: frm.doc.breakup_workbook },
				freeze: true,
				freeze_message: __("Importing..."),
				callback: function (r) {
					frm.reload_doc();
					if (r.message) {
						frappe.show_alert({
							message: __("Imported {0} row(s).", [r.message.row_count]),
							indicator: "green",
						});
					}
				},
			});
		}
	);
};
