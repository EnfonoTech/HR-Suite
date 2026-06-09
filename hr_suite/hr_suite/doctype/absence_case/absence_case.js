const ABSENCE_CASE_SECTION_DESCRIPTIONS = {
	absence_section: "Record the absence period, its type, and any notice deadline sent to the employee.",
	details_section: "Capture the employee response and any escalation or disciplinary linkage.",
};


frappe.ui.form.on("Absence Case", {
	refresh(frm) {
		apply_absence_case_section_descriptions(frm, ABSENCE_CASE_SECTION_DESCRIPTIONS);
	},
});


function apply_absence_case_section_descriptions(frm, descriptions) {
	for (const [fieldname, description] of Object.entries(descriptions)) {
		frm.set_df_property(fieldname, "description", __(description));
	}
	frm.refresh_fields(Object.keys(descriptions));
}