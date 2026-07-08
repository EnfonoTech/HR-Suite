frappe.ui.form.on("Salary Structure Assignment Import", {
	refresh: function (frm) {
		frm.add_custom_button(__("Download Template"), function () {
			hr_suite_ssai.download_template(frm);
		});

		if (frm.doc.workbook) {
			frm.add_custom_button(__("Import Workbook"), function () {
				hr_suite_ssai.import_workbook(frm);
			}).addClass("btn-primary");
		}

		hr_suite_ssai.render_log(frm);
	},

	workbook: function (frm) {
		frm.refresh();
	},
});

frappe.provide("hr_suite_ssai");

hr_suite_ssai.download_template = function (frm) {
	if (!frm.doc.company) {
		frappe.msgprint(__("Please select a Company first."));
		return;
	}
	const proceed = function () {
		frappe.call({
			method: "hr_suite.hr_suite.doctype.salary_structure_assignment_import.salary_structure_assignment_import.download_template",
			args: { doc_name: frm.doc.name },
			freeze: true,
			freeze_message: __("Building template..."),
			callback: function (r) {
				if (r.message && r.message.file_url) {
					window.open(r.message.file_url);
					frappe.show_alert({
						message: __("Template ready with {0} employee row(s).", [r.message.row_count]),
						indicator: "green",
					});
				}
			},
		});
	};
	if (frm.is_new()) {
		frm.save().then(proceed);
	} else {
		proceed();
	}
};

hr_suite_ssai.import_workbook = function (frm) {
	frappe.confirm(
		__("This will create and submit a Salary Structure Assignment for each valid row in the workbook. Continue?"),
		function () {
			frappe.call({
				method: "hr_suite.hr_suite.doctype.salary_structure_assignment_import.salary_structure_assignment_import.import_workbook",
				args: { doc_name: frm.doc.name },
				freeze: true,
				freeze_message: __("Importing..."),
				callback: function (r) {
					frm.reload_doc();
					if (r.message && r.message.queued) {
						frappe.show_alert({
							message: __("{0} rows queued for background import. Refresh shortly for results.", [
								r.message.total_rows,
							]),
							indicator: "blue",
						});
						return;
					}
					if (r.message) {
						hr_suite_ssai.show_result_dialog(r.message);
					}
				},
			});
		}
	);
};

hr_suite_ssai.render_log = function (frm) {
	if (!frm.doc.import_log) return;
	let results;
	try {
		results = JSON.parse(frm.doc.import_log);
	} catch (e) {
		return;
	}
	if (!Array.isArray(results) || !results.length) return;

	frm.dashboard.clear_headline();
	frm.dashboard.set_headline(
		__("Assigned: {0} · Skipped: {1} · Failed: {2}", [
			frm.doc.success_count || 0,
			frm.doc.skipped_count || 0,
			frm.doc.failed_count || 0,
		])
	);
};

hr_suite_ssai.show_result_dialog = function (summary) {
	const rows = summary.results || [];
	const status_color = { Assigned: "green", Skipped: "orange", Failed: "red" };

	let html = `<div class="text-muted margin-bottom">
		${__("Assigned")}: <strong>${summary.success_count}</strong> &nbsp;
		${__("Skipped")}: <strong>${summary.skipped_count}</strong> &nbsp;
		${__("Failed")}: <strong>${summary.failed_count}</strong>
	</div>
	<table class="table table-bordered table-sm">
		<thead><tr>
			<th>${__("Row")}</th>
			<th>${__("Employee")}</th>
			<th>${__("Salary Structure")}</th>
			<th>${__("Status")}</th>
			<th>${__("Message")}</th>
		</tr></thead>
		<tbody>`;

	rows.forEach(function (row) {
		const color = status_color[row.status] || "dark";
		html += `<tr>
			<td>${frappe.utils.escape_html(row.row)}</td>
			<td>${frappe.utils.escape_html(row.employee || "")}</td>
			<td>${frappe.utils.escape_html(row.salary_structure || "")}</td>
			<td><span class="indicator ${color}">${frappe.utils.escape_html(row.status)}</span></td>
			<td>${frappe.utils.escape_html(row.message || "")}</td>
		</tr>`;
	});

	html += "</tbody></table>";

	const d = new frappe.ui.Dialog({
		title: __("Import Results"),
		size: "extra-large",
		fields: [{ fieldname: "results_html", fieldtype: "HTML" }],
		primary_action_label: __("Close"),
		primary_action: function () {
			d.hide();
		},
	});
	d.fields_dict.results_html.$wrapper.html(html);
	d.show();
};
