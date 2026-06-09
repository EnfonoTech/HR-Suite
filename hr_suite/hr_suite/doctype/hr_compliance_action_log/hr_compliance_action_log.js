const HR_COMPLIANCE_ACTION_LOG_SECTION_DESCRIPTIONS = {
	action_section: "Plan the action owner, date, priority, and deadline before execution starts.",
	reference_section: "Link this action to the source record or employee that triggered the compliance work.",
	execution_section: "Document the corrective action, supporting evidence, and the final result.",
};


frappe.ui.form.on("HR Compliance Action Log", {
	refresh(frm) {
		apply_hr_compliance_action_log_section_descriptions(frm, HR_COMPLIANCE_ACTION_LOG_SECTION_DESCRIPTIONS);
	},
});


function apply_hr_compliance_action_log_section_descriptions(frm, descriptions) {
	for (const [fieldname, description] of Object.entries(descriptions)) {
		frm.set_df_property(fieldname, "description", __(description));
	}
	frm.refresh_fields(Object.keys(descriptions));
}