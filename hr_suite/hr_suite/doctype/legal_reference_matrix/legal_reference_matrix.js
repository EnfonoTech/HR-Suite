const LEGAL_REFERENCE_MATRIX_SECTION_DESCRIPTIONS = {
	reference_section: "Register the legal article, its effective date, and the internal owner responsible for monitoring it.",
	obligation_section: "Map each legal obligation to a control, policy, and evidence requirement.",
};


frappe.ui.form.on("Legal Reference Matrix", {
	refresh(frm) {
		apply_legal_reference_matrix_section_descriptions(frm, LEGAL_REFERENCE_MATRIX_SECTION_DESCRIPTIONS);

		if (!frm.is_new() && frm.doc.status !== "Retired") {
			frm.add_custom_button(__("Create Regulatory Task"), async function () {
				const response = await frappe.call({
					method: "hr_suite.hr_suite.doctype.legal_reference_matrix.legal_reference_matrix.create_regulatory_task",
					args: { reference_name: frm.doc.name },
				});
				await frm.reload_doc();
				if (response.message?.task_name) {
					frappe.set_route("Form", "Regulatory Task", response.message.task_name);
				}
			});
		}
	},
});


function apply_legal_reference_matrix_section_descriptions(frm, descriptions) {
	for (const [fieldname, description] of Object.entries(descriptions)) {
		frm.set_df_property(fieldname, "description", __(description));
	}
	frm.refresh_fields(Object.keys(descriptions));
}