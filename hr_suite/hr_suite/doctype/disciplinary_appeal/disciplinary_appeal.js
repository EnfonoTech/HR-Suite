const DISCIPLINARY_APPEAL_SECTION_DESCRIPTIONS = {
	appeal_section: "Record the appeal type, submission date, assignee, and hearing schedule.",
	details_section: "Capture the grounds, committee review notes, and final appeal decision.",
};


frappe.ui.form.on("Disciplinary Appeal", {
	refresh(frm) {
		apply_disciplinary_appeal_section_descriptions(frm, DISCIPLINARY_APPEAL_SECTION_DESCRIPTIONS);
	},
});


function apply_disciplinary_appeal_section_descriptions(frm, descriptions) {
	for (const [fieldname, description] of Object.entries(descriptions)) {
		frm.set_df_property(fieldname, "description", __(description));
	}
	frm.refresh_fields(Object.keys(descriptions));
}