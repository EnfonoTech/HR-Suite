// HR Suite — WPS / Mudad actions injected into Payroll Entry and Salary Slip List

// ── Payroll Entry form ───────────────────────────────────────────────────────
frappe.ui.form.on("Payroll Entry", {
	refresh(frm) {
		if (frm.is_new()) return;

		frappe.db.get_value("Hr Suite Settings", null, "mudad_enabled").then(r => {
			if (!r.message || !r.message.mudad_enabled) return;

			// Only show after payroll is submitted
			if (frm.doc.docstatus !== 1) return;

			frm.add_custom_button(__("Preview WPS File"), function () {
				_preview_wps(frm);
			}, __("WPS / Mudad"));

			frm.add_custom_button(__("Submit WPS to Mudad"), function () {
				_submit_wps(frm);
			}, __("WPS / Mudad"));

			frm.add_custom_button(__("Check WPS Status"), function () {
				_check_wps_status(frm);
			}, __("WPS / Mudad"));

			frm.add_custom_button(__("Sync Log"), function () {
				frappe.set_route("List", "Government Portal Sync Log", { portal: "Mudad" });
			}, __("WPS / Mudad"));
		});
	},
});

function _month_from_date(date_str) {
	const months = ["January","February","March","April","May","June",
	                "July","August","September","October","November","December"];
	const d = frappe.datetime.str_to_obj(date_str);
	return { month: months[d.getMonth()], year: String(d.getFullYear()) };
}

function _preview_wps(frm) {
	const { month, year } = _month_from_date(frm.doc.start_date);
	frappe.call({
		method: "hr_suite.hr_suite.integrations.mudad.generate_wps_file",
		args: { company: frm.doc.company, month, year },
		freeze: true,
		freeze_message: __("Building WPS file…"),
		callback(r) {
			if (r.exc || !r.message) return;
			const d = r.message;
			const rows = (d.rows || []).map(e =>
				`<tr><td>${e.employee_id}</td><td>${e.employee_name}</td>`+
				`<td>${e.employee_iban || "—"}</td><td>${frappe.format(e.net_salary, {fieldtype:"Currency"})}</td></tr>`
			).join("");
			frappe.msgprint({
				title: __(`WPS File Preview — ${month} ${year}`),
				message: `<p>${__("Employees")}: <b>${d.employee_count}</b> &nbsp;|&nbsp; `+
				         `${__("Total Net")}: <b>${frappe.format(d.total_net_salary,{fieldtype:"Currency"})}</b></p>`+
				         `<div style="max-height:300px;overflow-y:auto"><table class="table table-condensed table-bordered">`+
				         `<thead><tr><th>ID</th><th>Name</th><th>IBAN</th><th>Net Salary</th></tr></thead>`+
				         `<tbody>${rows}</tbody></table></div>`,
				indicator: "blue",
			});
		},
	});
}

function _submit_wps(frm) {
	const { month, year } = _month_from_date(frm.doc.start_date);
	frappe.confirm(
		__(`Submit WPS salary file for ${month} ${year} to Mudad portal?`),
		function () {
			frappe.call({
				method: "hr_suite.hr_suite.integrations.mudad.submit_wps_file",
				args: { company: frm.doc.company, month, year },
				freeze: true,
				freeze_message: __("Submitting to Mudad…"),
				callback(r) {
					if (r.exc || !r.message) return;
					const d = r.message;
					frappe.show_alert({
						message: __(`WPS submitted — Ref: ${d.reference_number || "—"} | Status: ${d.status || "—"}`),
						indicator: "green",
					});
				},
			});
		}
	);
}

function _check_wps_status(frm) {
	const { month, year } = _month_from_date(frm.doc.start_date);
	frappe.call({
		method: "hr_suite.hr_suite.integrations.mudad.get_wps_status",
		args: { company: frm.doc.company, month, year },
		callback(r) {
			if (r.exc || !r.message) return;
			const d = r.message;
			const compliant = d.is_compliant;
			frappe.msgprint({
				title: __(`WPS Status — ${d.period}`),
				message: `<table class="table table-condensed">
					<tr><td>${__("Status")}</td><td><b>${d.status || "—"}</b></td></tr>
					<tr><td>${__("Compliant")}</td><td><b>${compliant ? "✔ Yes" : "✘ No"}</b></td></tr>
					<tr><td>${__("Employees")}</td><td>${d.employee_count || "—"}</td></tr>
					<tr><td>${__("Total Salary")}</td><td>${frappe.format(d.total_salary,{fieldtype:"Currency"})}</td></tr>
					<tr><td>${__("Submitted On")}</td><td>${d.submitted_on || "—"}</td></tr>
					${d.violation_reason ? `<tr><td>${__("Violation")}</td><td class="text-danger">${d.violation_reason}</td></tr>` : ""}
				</table>`,
				indicator: compliant ? "green" : "red",
			});
		},
	});
}
