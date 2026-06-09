const INVESTIGATION_RECORD_SECTION_DESCRIPTIONS = {
	reference_section: "Identify the source case, allegation date, and assigned investigator.",
	timeline_section: "Track the lifecycle of the investigation from opening to closure.",
	details_section: "Write the allegation, employee statement, findings, and recommended outcome.",
};


frappe.ui.form.on("Investigation Record", {
	refresh(frm) {
		apply_investigation_record_section_descriptions(frm, INVESTIGATION_RECORD_SECTION_DESCRIPTIONS);

		if (!frm.is_new() && (frm.doc.investigation_end_date || frm.doc.findings)) {
			frm.add_custom_button(__("Create Warning Notice"), async function () {
				const response = await frappe.call({
					method: "hr_suite.hr_suite.doctype.investigation_record.investigation_record.create_warning_notice",
					args: { record_name: frm.doc.name },
				});
				await frm.reload_doc();
				if (response.message?.warning_notice) {
					frappe.set_route("Form", "Employee Warning Notice", response.message.warning_notice);
				}
			});
		}
	},
});


function apply_investigation_record_section_descriptions(frm, descriptions) {
	for (const [fieldname, description] of Object.entries(descriptions)) {
		frm.set_df_property(fieldname, "description", __(description));
	}
	frm.refresh_fields(Object.keys(descriptions));
}