frappe.ui.form.on("Saudi Employee Voice Profile", {
	refresh(frm) {
		if (frm.is_new() || !frm.has_perm("write")) {
			return;
		}

		frm.add_custom_button(__("Reset Voice Enrollment"), () => {
			frappe.confirm(
				__("Reset the saved voiceprint and allow the employee to enroll again from mobile attendance?"),
				async () => {
					const response = await frappe.call({
						method: "hr_suite.hr_suite.voice_verification.reset_employee_voice_profile",
						args: {
							profile_name: frm.doc.name,
						},
					});
					frappe.show_alert({
						message: response.message?.message || __("Voice enrollment reset completed."),
						indicator: "green",
					});
					await frm.reload_doc();
				}
			);
		});
	},
});