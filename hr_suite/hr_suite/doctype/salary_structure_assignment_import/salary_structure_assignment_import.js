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

		// Retry failed rows
		if (frm.doc.status === "Completed with Errors" && frm.doc.failed_count > 0) {
			frm.add_custom_button(__("Retry Failed Rows ({0})", [frm.doc.failed_count]), function () {
				hr_suite_ssai.retry_failed_rows(frm);
			}).addClass("btn-warning");
		}

		// Cancel all assignments created by this import
		const cancellable = ["Completed", "Completed with Errors"].includes(frm.doc.status);
		if (cancellable && frm.doc.success_count > 0) {
			frm.add_custom_button(__("Cancel Assignments"), function () {
				hr_suite_ssai.cancel_import(frm);
			}).addClass("btn-danger");
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
	const has_breakup = rows.some(r => r.total_salary != null);
	const has_ssa = rows.some(r => r.ssa_name);

	let html = `<div class="text-muted margin-bottom">
		${__("Assigned")}: <strong>${summary.success_count}</strong> &nbsp;
		${__("Skipped")}: <strong>${summary.skipped_count}</strong> &nbsp;
		${__("Failed")}: <strong>${summary.failed_count}</strong>
	</div>
	<div style="overflow-x:auto;">
	<table class="table table-bordered table-sm">
		<thead><tr>
			<th>${__("Row")}</th>
			<th>${__("Employee")}</th>
			<th>${__("Salary Structure")}</th>
			${has_breakup ? `<th style="text-align:right;">${__("Total Salary")}</th><th style="text-align:right;">${__("Band Applied")}</th>` : ""}
			<th>${__("Status")}</th>
			<th>${__("Message")}</th>
			${has_ssa ? `<th>${__("Assignment")}</th>` : ""}
		</tr></thead>
		<tbody>`;

	rows.forEach(function (row) {
		const color = status_color[row.status] || "dark";
		const fmt_sal = row.total_salary ? frappe.format(row.total_salary, { fieldtype: "Currency" }) : "";
		const fmt_band = row.breakup_band ? frappe.format(row.breakup_band, { fieldtype: "Currency" }) : (row.total_salary ? '<span style="color:#e74c3c">—</span>' : "");
		const ssa_link = row.ssa_name
			? `<a href="/app/salary-structure-assignment/${encodeURIComponent(row.ssa_name)}" target="_blank" style="font-size:11px;">${frappe.utils.escape_html(row.ssa_name)}</a>`
			: "";
		html += `<tr>
			<td>${frappe.utils.escape_html(row.row)}</td>
			<td>${frappe.utils.escape_html(row.employee || "")}</td>
			<td>${frappe.utils.escape_html(row.salary_structure || "")}</td>
			${has_breakup ? `<td style="text-align:right;font-family:monospace;">${fmt_sal}</td><td style="text-align:right;font-family:monospace;">${fmt_band}</td>` : ""}
			<td><span class="indicator ${color}">${frappe.utils.escape_html(row.status)}</span></td>
			<td>${frappe.utils.escape_html(row.message || "")}</td>
			${has_ssa ? `<td>${ssa_link}</td>` : ""}
		</tr>`;
	});

	html += "</tbody></table></div>";

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

hr_suite_ssai.retry_failed_rows = function (frm) {
	frappe.confirm(
		__("Re-process the {0} failed row(s) from the original workbook?", [frm.doc.failed_count]),
		function () {
			frappe.call({
				method: "hr_suite.hr_suite.doctype.salary_structure_assignment_import.salary_structure_assignment_import.retry_failed_rows",
				args: { doc_name: frm.doc.name },
				freeze: true,
				freeze_message: __("Retrying failed rows..."),
				callback: function (r) {
					frm.reload_doc();
					if (r.message) {
						hr_suite_ssai.show_result_dialog(r.message);
					}
				},
			});
		}
	);
};

hr_suite_ssai.cancel_import = function (frm) {
	frappe.confirm(
		__("This will cancel all <b>{0}</b> Salary Structure Assignment(s) created by this import. This cannot be undone if salary slips already exist. Continue?", [frm.doc.success_count]),
		function () {
			frappe.call({
				method: "hr_suite.hr_suite.doctype.salary_structure_assignment_import.salary_structure_assignment_import.cancel_import",
				args: { doc_name: frm.doc.name },
				freeze: true,
				freeze_message: __("Cancelling assignments..."),
				callback: function (r) {
					frm.reload_doc();
					if (!r.message) return;
					const msg = r.message;
					if (msg.errors && msg.errors.length) {
						frappe.msgprint({
							title: __("Cancelled with Errors"),
							message: __("{0} assignment(s) cancelled. Could not cancel:<br>{1}", [
								msg.cancelled,
								msg.errors.map(e => frappe.utils.escape_html(e)).join("<br>"),
							]),
							indicator: "orange",
						});
					} else {
						frappe.show_alert({
							message: __("{0} assignment(s) cancelled.", [msg.cancelled]),
							indicator: "green",
						});
					}
				},
			});
		}
	);
};
