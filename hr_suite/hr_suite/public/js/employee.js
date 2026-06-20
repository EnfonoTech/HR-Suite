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

		// ── Muqeem buttons (SA employees only) ───────────────────────────────
		frappe.db.get_value("Hr Suite Settings", null, "muqeem_enabled").then(r => {
			if (!r.message || !r.message.muqeem_enabled) return;

			frm.add_custom_button(__("Verify Iqama"), function () {
				_muqeem_verify_iqama(frm);
			}, __("Muqeem"));

			frm.add_custom_button(__("Exit Re-entry Status"), function () {
				_muqeem_exit_reentry(frm);
			}, __("Muqeem"));

			frm.add_custom_button(__("Sync Log"), function () {
				frappe.set_route("List", "Government Portal Sync Log", {
					employee: frm.doc.name, portal: "Muqeem",
				});
			}, __("Muqeem"));
		});

		// ── Qiwa buttons (SA employees only) ─────────────────────────────────
		frappe.db.get_value("Hr Suite Settings", null, "qiwa_enabled").then(r => {
			if (!r.message || !r.message.qiwa_enabled) return;

			frm.add_custom_button(__("Verify Wathiqa Contract"), function () {
				_qiwa_verify_contract(frm);
			}, __("Qiwa"));

			frm.add_custom_button(__("Labor Notices"), function () {
				_qiwa_labor_notices(frm);
			}, __("Qiwa"));

			frm.add_custom_button(__("Sync Log"), function () {
				frappe.set_route("List", "Government Portal Sync Log", {
					employee: frm.doc.name, portal: "Qiwa",
				});
			}, __("Qiwa"));
		});

		// ── GOSI API buttons ──────────────────────────────────────────────────
		frappe.db.get_value("Hr Suite Settings", null, "gosi_api_enabled").then(r => {
			if (!r.message || !r.message.gosi_api_enabled) return;

			frm.add_custom_button(__("Register with GOSI"), function () {
				frappe.confirm(
					__(`Register ${frm.doc.employee_name} with GOSI?`),
					function () {
						frappe.call({
							method: "hr_suite.hr_suite.integrations.gosi_api.register_employee",
							args: { employee: frm.doc.name },
							freeze: true,
							freeze_message: __("Registering with GOSI…"),
							callback(res) {
								if (res.exc) return;
								frappe.show_alert({ message: __("Registered with GOSI successfully."), indicator: "green" });
							},
						});
					}
				);
			}, __("GOSI"));

			frm.add_custom_button(__("GOSI Member Status"), function () {
				frappe.call({
					method: "hr_suite.hr_suite.integrations.gosi_api.get_employee_status",
					args: { employee: frm.doc.name },
					callback(res) {
						if (res.exc || !res.message) return;
						const d = res.message;
						frappe.msgprint({
							title: __("GOSI Member Status"),
							message: `<table class="table table-condensed">
								<tr><td>${__("Status")}</td><td><b>${d.gosi_status || "—"}</b></td></tr>
								<tr><td>${__("Registration Date")}</td><td>${d.registration_date || "—"}</td></tr>
								<tr><td>${__("Last Contribution")}</td><td>${d.last_contribution_month || "—"}</td></tr>
							</table>`,
							indicator: "blue",
						});
					},
				});
			}, __("GOSI"));

			frm.add_custom_button(__("Deregister from GOSI"), function () {
				let d = new frappe.ui.Dialog({
					title: __("Deregister from GOSI"),
					fields: [
						{ fieldname: "exit_date", fieldtype: "Date", label: "Exit Date", reqd: 1 },
						{ fieldname: "reason", fieldtype: "Select", label: "Reason", reqd: 1,
						  options: "Resignation\nTermination\nEnd of Contract\nDeath\nRetirement" },
					],
					primary_action_label: __("Deregister"),
					primary_action(vals) {
						frappe.confirm(
							__(`Deregister ${frm.doc.employee_name} from GOSI? This cannot be undone.`),
							function () {
								frappe.call({
									method: "hr_suite.hr_suite.integrations.gosi_api.deregister_employee",
									args: { employee: frm.doc.name, exit_date: vals.exit_date, reason: vals.reason },
									freeze: true,
									freeze_message: __("Deregistering from GOSI…"),
									callback(res) {
										if (res.exc) return;
										frappe.show_alert({ message: __("Deregistered from GOSI."), indicator: "orange" });
										d.hide();
									},
								});
							}
						);
					},
				});
				d.show();
			}, __("GOSI"));

			frm.add_custom_button(__("Sync Log"), function () {
				frappe.set_route("List", "Government Portal Sync Log", {
					employee: frm.doc.name, portal: "GOSI",
				});
			}, __("GOSI"));
		});
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

// ── Muqeem helpers ────────────────────────────────────────────────────────────

function _muqeem_verify_iqama(frm) {
	frappe.db.get_value("Work Permit / Iqama", { employee: frm.doc.name }, "iqama_number", function(r) {
		const prefill = r && r.iqama_number ? r.iqama_number : "";
		frappe.prompt(
			[{ label: __("Iqama Number"), fieldname: "iqama_number", fieldtype: "Data", reqd: 1, default: prefill }],
			function(vals) {
				frappe.show_progress(__("Verifying Iqama…"), 0, 100);
				frappe.call({
					method: "hr_suite.hr_suite.integrations.muqeem.verify_iqama",
					args: { iqama_number: vals.iqama_number, employee: frm.doc.name },
					callback(res) {
						frappe.hide_progress();
						if (res.exc) return;
						const d = res.message || {};
						frappe.msgprint({
							title: __("Muqeem — Iqama Verified"),
							message: `<table class="table table-bordered table-sm" style="font-size:13px;">
								<tr><td><b>Status</b></td><td>${d.status || "—"}</td></tr>
								<tr><td><b>Expiry Date</b></td><td>${d.expiry_date || "—"}</td></tr>
								<tr><td><b>Name (EN)</b></td><td>${d.full_name_en || "—"}</td></tr>
								<tr><td><b>Profession</b></td><td>${d.profession || "—"}</td></tr>
								<tr><td><b>Nationality</b></td><td>${d.nationality || "—"}</td></tr>
								<tr><td><b>Sponsor</b></td><td>${d.sponsor_name || "—"}</td></tr>
							</table>`,
							indicator: d.status === "Valid" ? "green" : "orange",
						});
						frm.reload_doc();
					},
				});
			},
			__("Verify Iqama — Muqeem"), __("Verify")
		);
	});
}

function _muqeem_exit_reentry(frm) {
	frappe.db.get_value("Work Permit / Iqama", { employee: frm.doc.name }, "iqama_number", function(r) {
		if (!r || !r.iqama_number) { frappe.msgprint(__("No Iqama record found.")); return; }
		frappe.call({
			method: "hr_suite.hr_suite.integrations.muqeem.get_exit_reentry",
			args: { iqama_number: r.iqama_number, employee: frm.doc.name },
			callback(res) {
				if (res.exc) return;
				const d = res.message || {};
				frappe.msgprint({
					title: __("Muqeem — Exit Re-entry Status"),
					message: `<table class="table table-bordered table-sm" style="font-size:13px;">
						<tr><td><b>Visa Number</b></td><td>${d.visa_number || "—"}</td></tr>
						<tr><td><b>Expiry Date</b></td><td>${d.expiry_date || "—"}</td></tr>
						<tr><td><b>Type</b></td><td>${d.visa_type || "—"}</td></tr>
						<tr><td><b>Status</b></td><td>${d.status || "—"}</td></tr>
					</table>`,
					indicator: "blue",
				});
				frm.reload_doc();
			},
		});
	});
}

// ── Qiwa helpers ──────────────────────────────────────────────────────────────

function _qiwa_verify_contract(frm) {
	frappe.db.get_value("Work Permit / Iqama", { employee: frm.doc.name }, "iqama_number", function(r) {
		if (!r || !r.iqama_number) { frappe.msgprint(__("No Iqama record found.")); return; }
		frappe.show_progress(__("Contacting Qiwa…"), 0, 100);
		frappe.call({
			method: "hr_suite.hr_suite.integrations.qiwa.verify_contract",
			args: { iqama_number: r.iqama_number, employee: frm.doc.name },
			callback(res) {
				frappe.hide_progress();
				if (res.exc) return;
				const d = res.message || {};
				frappe.msgprint({
					title: __("Qiwa — Wathiqa Contract"),
					message: `<table class="table table-bordered table-sm" style="font-size:13px;">
						<tr><td><b>Contract ID</b></td><td>${d.contract_id || "—"}</td></tr>
						<tr><td><b>Status</b></td><td>${d.contract_status || "—"}</td></tr>
						<tr><td><b>Job Title</b></td><td>${d.job_title || "—"}</td></tr>
						<tr><td><b>Salary</b></td><td>${d.salary ? frappe.format(d.salary, {fieldtype:"Currency"}) : "—"}</td></tr>
						<tr><td><b>Start Date</b></td><td>${d.start_date || "—"}</td></tr>
						<tr><td><b>End Date</b></td><td>${d.end_date || "—"}</td></tr>
						<tr><td><b>Verified</b></td><td>${d.is_verified ? "✅ Yes" : "❌ No"}</td></tr>
					</table>`,
					indicator: d.contract_status === "Active" ? "green" : "orange",
				});
			},
		});
	});
}

function _qiwa_labor_notices(frm) {
	frappe.db.get_value("Work Permit / Iqama", { employee: frm.doc.name }, "iqama_number", function(r) {
		const iqama = r && r.iqama_number ? r.iqama_number : null;
		frappe.call({
			method: "hr_suite.hr_suite.integrations.qiwa.get_labor_notices",
			args: { employee: frm.doc.name, iqama_number: iqama },
			callback(res) {
				if (res.exc) return;
				const notices = res.message || [];
				if (!notices.length) { frappe.show_alert({ message: __("No labor notices found."), indicator: "green" }); return; }
				const rows = notices.map(n => `<tr><td>${n.notice_type || n.type || "—"}</td><td>${n.notice_date || n.date || "—"}</td><td>${n.status || "—"}</td><td>${n.description || "—"}</td></tr>`).join("");
				frappe.msgprint({
					title: __(`Qiwa — Labor Notices (${notices.length})`),
					message: `<table class="table table-bordered table-sm" style="font-size:12px;">
						<thead><tr><th>Type</th><th>Date</th><th>Status</th><th>Details</th></tr></thead>
						<tbody>${rows}</tbody></table>`,
					indicator: "blue",
				});
			},
		});
	});
}
