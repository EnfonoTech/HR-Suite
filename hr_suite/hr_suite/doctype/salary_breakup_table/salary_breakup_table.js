frappe.ui.form.on("Salary Breakup Table", {
	refresh: function (frm) {
		frm.add_custom_button(__("Import Breakup Table"), function () {
			hr_suite_breakup.import_table(frm);
		});
	},
});

frappe.provide("hr_suite_breakup");

hr_suite_breakup.import_table = function (frm) {
	if (frm.is_new()) {
		frappe.msgprint(__("Save the record first — select a company and save before importing."));
		return;
	}
	if (!frm.doc.breakup_workbook) {
		frappe.msgprint(__("Attach a Salary Breakup Workbook first."));
		return;
	}

	frappe.confirm(
		__("This will replace the current Breakup Rows for <b>{0}</b> with the rows from the attached workbook. Continue?", [frm.doc.company]),
		function () {
			frappe.call({
				method: "hr_suite.hr_suite.doctype.salary_breakup_table.salary_breakup_table.import_breakup_table",
				args: { doc_name: frm.doc.name, file_url: frm.doc.breakup_workbook },
				freeze: true,
				freeze_message: __("Importing..."),
				callback: function (r) {
					frm.reload_doc();
					if (r.message) {
						frappe.show_alert({
							message: __("Imported {0} row(s) for {1}.", [r.message.row_count, frm.doc.company]),
							indicator: "green",
						});
						hr_suite_breakup.maybe_prompt_create_structure(frm);
					}
				},
			});
		}
	);
};

hr_suite_breakup.maybe_prompt_create_structure = function (frm) {
	const company = frm.doc.company;
	const struct_name = company + " Common Structure";

	frappe.db.exists("Salary Structure", struct_name).then(function (exists) {
		if (exists) return;

		const components = [
			"Basic → formula: <code>base</code>",
			"HRA / Living Allowances → formula: <code>custom_hra_amount</code>",
			"Transport / Food Allowance → formula: <code>custom_transport_amount</code>",
			"Other Allowance → formula: <code>custom_other_allowance_amount</code>",
		];

		frappe.confirm(
			`<p>${__("Would you like to create a draft <b>Monthly Salary Structure</b> for <b>{0}</b>?", [company])}</p>
			<p style="font-size:12px;color:#6c757d;">${__("Structure name")}: <b>${struct_name}</b></p>
			<ul style="font-size:12px;margin-top:8px;">
				${components.map(c => `<li>${c}</li>`).join("")}
			</ul>
			<p style="font-size:12px;color:#e67e22;">
				${__("The structure will be saved as <b>Draft</b>. Review taxability and other settings before submitting.")}
			</p>`,
			function () {
				frappe.call({
					method: "hr_suite.hr_suite.doctype.salary_breakup_table.salary_breakup_table.create_salary_structure_from_breakup",
					args: { company },
					freeze: true,
					freeze_message: __("Creating Salary Structure..."),
					callback: function (r) {
						if (!r.message) return;
						const name = r.message.name;
						const currency = r.message.currency;
						const comps = (r.message.components || []).join(", ");

						frappe.show_alert({
							message: __("Draft Salary Structure <b>{0}</b> created ({1}). Open and submit when ready.", [name, currency]),
							indicator: "blue",
						});

						// Offer to open it immediately
						const d = new frappe.ui.Dialog({
							title: __("Salary Structure Created"),
							fields: [
								{
									fieldtype: "HTML",
									options: `
										<div style="padding:8px 0;">
											<p><b>${name}</b> has been created as a draft.</p>
											<p style="font-size:12px;color:#6c757d;">Components: ${frappe.utils.escape_html(comps)}</p>
											<p style="font-size:12px;">Review taxability, GOSI exemptions, and payment days settings before submitting.</p>
										</div>
									`,
								},
							],
							primary_action_label: __("Open Salary Structure"),
							primary_action: function () {
								d.hide();
								frappe.set_route("Form", "Salary Structure", name);
							},
							secondary_action_label: __("Close"),
							secondary_action: function () { d.hide(); },
						});
						d.show();
					},
				});
			}
		);
	});
};
