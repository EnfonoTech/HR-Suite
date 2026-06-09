const EMPLOYEE_GRIEVANCE_SECTION_DESCRIPTIONS = {
	grievance_section: "Register how the grievance was received, its type, and the assigned owner.",
	response_section: "Track due dates, first response, and final resolution timing.",
	details_section: "Summarize the grievance facts, requested remedy, and resolution outcome.",
};


frappe.ui.form.on("Employee Grievance", {
	refresh(frm) {
		apply_employee_grievance_section_descriptions(frm, EMPLOYEE_GRIEVANCE_SECTION_DESCRIPTIONS);
	},
});


function apply_employee_grievance_section_descriptions(frm, descriptions) {
	for (const [fieldname, description] of Object.entries(descriptions)) {
		frm.set_df_property(fieldname, "description", __(description));
	}
	frm.refresh_fields(Object.keys(descriptions));
}