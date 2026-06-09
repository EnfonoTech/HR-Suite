const HR_POLICY_DOCUMENT_SECTION_DESCRIPTIONS = {
	policy_section: "Define when the policy starts, when it should be reviewed, and who owns it.",
	legal_section: "Capture the legal basis and risk level that justify this policy.",
	document_section: "Store the policy summary and the latest approved attachment for operational use.",
};


frappe.ui.form.on("HR Policy Document", {
	refresh(frm) {
		apply_hr_policy_document_section_descriptions(frm, HR_POLICY_DOCUMENT_SECTION_DESCRIPTIONS);

		if (!frm.is_new() && frm.doc.acknowledgement_required && frm.doc.status === "Active") {
			frm.add_custom_button(__("Sync Acknowledgements"), async function () {
				const response = await frappe.call({
					method: "hr_suite.hr_suite.doctype.hr_policy_document.hr_policy_document.sync_policy_acknowledgements",
					args: { policy_name: frm.doc.name },
				});
				await frm.reload_doc();
				frappe.show_alert({
					message: __("Created {0} acknowledgement records", [response.message.created || 0]),
					indicator: "green",
				});
			});
		}
	},
});


function apply_hr_policy_document_section_descriptions(frm, descriptions) {
	for (const [fieldname, description] of Object.entries(descriptions)) {
		frm.set_df_property(fieldname, "description", __(description));
	}
	frm.refresh_fields(Object.keys(descriptions));
}