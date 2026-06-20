frappe.ui.form.on("WPS Submission", {
	refresh(frm) {
		if (frm.doc.payroll_document) {
			frm.add_custom_button(__("Open Payroll"), () => {
				frappe.set_route("Form", "Monthly Payroll", frm.doc.payroll_document);
			});

			frm.add_custom_button(__("Download WPS SIF File"), () => {
				window.location.href = frappe.urllib.get_full_url(
					`/api/method/hr_suite.hr_suite.report.wps_export_report.wps_export_report.download_wps_sif?payroll_document=${encodeURIComponent(frm.doc.payroll_document)}`
				);
			});
		}

		if (frm.doc.corrective_action_log) {
			frm.add_custom_button(__("Open Compliance Action"), () => {
				frappe.set_route("Form", "HR Compliance Action Log", frm.doc.corrective_action_log);
			});
		}
	},
});