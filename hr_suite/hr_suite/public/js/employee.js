// HR Suite — Employee Form Extensions
frappe.ui.form.on("Employee", {
	onload: function (frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(__("Active Contract"), function () {
			frappe.set_route("List", "Saudi Employment Contract", {
				employee: frm.doc.name,
				contract_status: "Active",
			});
		}, __("HR Suite"));

		frm.add_custom_button(__("Leave Balance"), function () {
			frappe.set_route("query-report", "Saudi Leave Balance Report", {
				employee: frm.doc.name,
			});
		}, __("HR Suite"));

		frm.add_custom_button(__("Onboarding"), function () {
			frappe.set_route("List", "Employee Onboarding", {
				employee: frm.doc.name,
			});
		}, __("HR Suite"));

		frm.add_custom_button(__("EOSB Estimate"), function () {
			let joining = frm.doc.date_of_joining;
			let gosi_base = frm.doc.hr_suite_gosi_salary || 0;
			if (!joining || !gosi_base) {
				frappe.msgprint(__("Set Date of Joining and GOSI Contribution Base on this Employee to get an estimate."));
				return;
			}
			frappe.call({
				method: "hr_suite.hr_suite.doctype.end_of_service_benefit.end_of_service_benefit.calculate_eosb_preview",
				args: {
					joining_date: joining,
					termination_date: frappe.datetime.get_today(),
					last_basic_salary: gosi_base,
					termination_reason: "Resignation by Employee",
					eosb_deductions: 0,
				},
				callback: function (r) {
					if (!r.message) return;
					let d = r.message;
					frappe.msgprint({
						title: __("EOSB Estimate (as of today)"),
						message: `<table class="table table-condensed" style="margin-top:8px">
							<tr><td>${__("Years of Service")}</td><td><b>${d.years_of_service}</b></td></tr>
							<tr><td>${__("Gross EOSB")}</td><td><b>${format_currency(d.eosb_gross)}</b></td></tr>
							<tr><td>${__("Net EOSB")}</td><td><b>${format_currency(d.net_eosb)}</b></td></tr>
						</table>
						<small class="text-muted">${d.calculation_notes || ""}</small>`,
						indicator: "blue",
					});
				},
			});
		}, __("HR Suite"));

		frm.add_custom_button(__("Disciplinary History"), function () {
			frappe.set_route("List", "Disciplinary Procedure", {
				employee: frm.doc.name,
			});
		}, __("HR Suite"));

		frm.add_custom_button(__("Penalties"), function () {
			frappe.set_route("List", "Employee Penalty", {
				employee: frm.doc.name,
			});
		}, __("HR Suite"));
	},

	refresh: function (frm) {
		if (frm.is_new()) return;
		_hr_suite_document_alerts(frm);
		_hr_suite_contract_banner(frm);
		_hr_suite_onboarding_banner(frm);
	},
});

function _hr_suite_document_alerts(frm) {
	frappe.db
		.get_list("Work Permit Iqama", {
			filters: { employee: frm.doc.name },
			fields: ["document_type", "expiry_date"],
			limit: 10,
			order_by: "expiry_date asc",
		})
		.then(function (docs) {
			if (!docs || !docs.length) return;
			let today = frappe.datetime.get_today();
			docs.forEach(function (doc) {
				if (!doc.expiry_date) return;
				let days = frappe.datetime.get_diff(doc.expiry_date, today);
				if (days <= 0) {
					frm.dashboard.add_comment(
						__("{0} EXPIRED on {1}", [doc.document_type || "Document", doc.expiry_date]),
						"red",
						true
					);
				} else if (days <= 30) {
					frm.dashboard.add_comment(
						__("{0} expires in {1} days ({2})", [doc.document_type || "Document", days, doc.expiry_date]),
						"orange",
						true
					);
				} else if (days <= 90) {
					frm.dashboard.add_comment(
						__("{0} expires in {1} days ({2})", [doc.document_type || "Document", days, doc.expiry_date]),
						"yellow",
						true
					);
				}
			});
		});
}

function _hr_suite_contract_banner(frm) {
	frappe.db
		.get_list("Saudi Employment Contract", {
			filters: { employee: frm.doc.name, contract_status: "Active" },
			fields: [
				"name",
				"basic_salary",
				"housing_allowance",
				"transport_allowance",
				"total_salary",
				"probation_end_date",
				"contract_type",
			],
			limit: 1,
		})
		.then(function (contracts) {
			if (!contracts || !contracts.length) return;
			let c = contracts[0];
			let prob = c.probation_end_date
				? ` &nbsp;|&nbsp; ${__("Probation ends")}: <b>${c.probation_end_date}</b>`
				: "";
			let emp_type = frm.doc.hr_suite_employee_type
				? ` &nbsp;|&nbsp; <b>${frm.doc.hr_suite_employee_type}</b>`
				: "";
			frm.dashboard.add_comment(
				`<b>${__("Active Contract")}:</b> ${c.contract_type}${emp_type}
				 &nbsp;|&nbsp; ${__("Basic")}: <b>${format_currency(c.basic_salary)}</b>
				 &nbsp;|&nbsp; ${__("Total")}: <b>${format_currency(c.total_salary)}</b>${prob}`,
				"blue",
				true
			);
		});
}

function _hr_suite_onboarding_banner(frm) {
	if (frm.doc.status !== "Active") return;
	frappe.db
		.get_list("Employee Onboarding", {
			filters: { employee: frm.doc.name, status: ["in", ["Draft", "In Progress"]] },
			fields: ["name", "status", "completion_percentage", "joining_date"],
			limit: 1,
		})
		.then(function (rows) {
			if (!rows || !rows.length) return;
			let r = rows[0];
			frm.dashboard.add_comment(
				`${__("Onboarding")} ${r.status}: <b>${r.completion_percentage}%</b> complete
				 — <a href="/app/employee-onboarding/${r.name}">${r.name}</a>`,
				"orange",
				true
			);
		});
}
