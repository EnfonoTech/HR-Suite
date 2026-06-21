// HR Suite — Employee Form Extensions (Global, Country-Aware)
frappe.ui.form.on("Employee", {
	refresh: function (frm) {
		if (frm.is_new()) return;

		// Resolve the employee's work country first, then build the full UI
		frappe.call({
			method: "hr_suite.hr_suite.utils.get_employee_work_country",
			args: { employee: frm.doc.name },
			callback: function (r) {
				const country = (r.message || "").toUpperCase();
				_hr_suite_common_buttons(frm, country);
				if (country === "SA") {
					_hr_suite_sa_buttons(frm);
				} else if (country === "AE") {
					_hr_suite_ae_buttons(frm);
				} else if (country === "BH") {
					_hr_suite_bh_buttons(frm);
				} else if (country === "IN") {
					_hr_suite_in_buttons(frm);
				} else if (country === "OM") {
					_hr_suite_om_buttons(frm);
				}
			},
		});

		_hr_suite_document_alerts(frm);
		_hr_suite_contract_banner(frm);
		_hr_suite_onboarding_banner(frm);
	},
});

// ── Common buttons shown for every country ────────────────────────────────────

function _hr_suite_common_buttons(frm, country) {
	// Active Contract — prefer Country Employment Contract, fallback Saudi for SA
	frm.add_custom_button(__("Active Contract"), function () {
		const doctype = country === "SA" ? "Saudi Employment Contract" : "Country Employment Contract";
		frappe.set_route("List", doctype, {
			employee: frm.doc.name,
			contract_status: "Active",
		});
	}, __("HR Suite"));

	frm.add_custom_button(__("Leave Balance"), function () {
		frappe.set_route("List", "Annual Leave", { employee: frm.doc.name });
	}, __("HR Suite"));

	frm.add_custom_button(__("Settlement Estimate"), function () {
		frappe.prompt(
			[
				{
					fieldname: "termination_reason",
					label: __("Termination Reason"),
					fieldtype: "Select",
					options: [
						"Resignation by Employee",
						"Termination by Employer",
						"End of Contract",
						"Retirement",
						"Death",
						"Disciplinary Dismissal (Article 80)",
					].join("\n"),
					reqd: 1,
					default: "Resignation by Employee",
				},
				{
					fieldname: "termination_date",
					label: __("As Of Date"),
					fieldtype: "Date",
					default: frappe.datetime.get_today(),
				},
			],
			function (values) {
				frappe.call({
					method: "hr_suite.hr_suite.utils.get_settlement_estimate",
					args: {
						employee: frm.doc.name,
						termination_reason: values.termination_reason,
						termination_date: values.termination_date || frappe.datetime.get_today(),
					},
					callback: function (r) {
						if (!r.message) return;
						let d = r.message;
						frappe.msgprint({
							title: __("Settlement Estimate"),
							message: `<table class="table table-condensed" style="margin-top:8px">
								<tr><td>${__("Country / Formula")}</td><td><b>${d.country || country} — ${d.formula || ""}</b></td></tr>
								<tr><td>${__("Years of Service")}</td><td><b>${flt(d.years_of_service, 2)}</b></td></tr>
								<tr><td>${__("Basic Salary")}</td><td><b>${format_currency(d.basic_salary)}</b></td></tr>
								<tr><td>${__("Gross Entitlement")}</td><td><b>${format_currency(d.gross_entitlement)}</b></td></tr>
								<tr><td>${__("Factor / Reason")}</td><td>${d.factor_label || ""}</td></tr>
								<tr><td>${__("Net Entitlement")}</td><td><b>${format_currency(d.net_entitlement)}</b></td></tr>
							</table>
							<small class="text-muted">${d.notes || ""}</small>`,
							indicator: "blue",
						});
					},
				});
			},
			__("Settlement Estimate"),
			__("Calculate")
		);
	}, __("HR Suite"));

	frm.add_custom_button(__("Onboarding"), function () {
		frappe.set_route("List", "Employee Onboarding", { employee: frm.doc.name });
	}, __("HR Suite"));

	frm.add_custom_button(__("Disciplinary History"), function () {
		frappe.set_route("List", "Disciplinary Procedure", { employee: frm.doc.name });
	}, __("HR Suite"));

	frm.add_custom_button(__("Penalties"), function () {
		frappe.set_route("List", "Employee Penalty", { employee: frm.doc.name });
	}, __("HR Suite"));

	frm.add_custom_button(__("Portal Sync Log"), function () {
		frappe.set_route("List", "Government Portal Sync Log", { employee: frm.doc.name });
	}, __("HR Suite"));
}

// ── Saudi Arabia buttons (Muqeem / Qiwa / GOSI) ───────────────────────────────

function _hr_suite_sa_buttons(frm) {
	const emp = frm.doc.name;

	// ── Muqeem (MOI) ──
	frappe.db.get_single_value("Hr Suite Settings", "muqeem_enabled").then(enabled => {
		if (!enabled) return;

		frm.add_custom_button(__("Verify Iqama"), function () {
			frappe.call({
				method: "hr_suite.hr_suite.integrations.muqeem.verify_iqama",
				args: { employee: emp },
				freeze: true,
				freeze_message: __("Checking Muqeem…"),
				callback(r) {
					if (r.exc) return;
					const d = r.message || {};
					frappe.msgprint({
						title: __("Iqama Status — Muqeem"),
						message: `<b>${__("Status")}:</b> ${d.status || "—"}<br>
							<b>${__("Expiry")}:</b> ${d.expiry_date || "—"}<br>
							<b>${__("Nationality")}:</b> ${d.nationality || "—"}`,
						indicator: d.status === "Valid" ? "green" : "red",
					});
					frm.reload_doc();
				},
			});
		}, __("Muqeem"));

		frm.add_custom_button(__("Exit / Re-entry Status"), function () {
			frappe.call({
				method: "hr_suite.hr_suite.integrations.muqeem.get_exit_reentry",
				args: { employee: emp },
				freeze: true,
				freeze_message: __("Checking Muqeem…"),
				callback(r) {
					if (r.exc) return;
					const d = r.message || {};
					frappe.msgprint({
						title: __("Exit / Re-entry Status"),
						message: `<b>${__("Status")}:</b> ${d.status || "—"}<br>
							<b>${__("Visa Type")}:</b> ${d.visa_type || "—"}<br>
							<b>${__("Expiry")}:</b> ${d.expiry_date || "—"}`,
						indicator: "blue",
					});
				},
			});
		}, __("Muqeem"));

		frm.add_custom_button(__("Initiate Final Exit"), function () {
			frappe.confirm(
				__("Submit a Final Exit request to Muqeem for this employee?"),
				function () {
					frappe.call({
						method: "hr_suite.hr_suite.integrations.muqeem.initiate_final_exit",
						args: { employee: emp },
						freeze: true,
						freeze_message: __("Submitting to Muqeem…"),
						callback(r) {
							if (r.exc) return;
							frappe.show_alert({ message: __("Final exit submitted to Muqeem."), indicator: "green" });
						},
					});
				}
			);
		}, __("Muqeem"));

		frm.add_custom_button(__("Sync Log"), function () {
			frappe.set_route("List", "Government Portal Sync Log", { employee: emp, portal: "Muqeem" });
		}, __("Muqeem"));
	});

	// ── Qiwa (HRSD) ──
	frappe.db.get_single_value("Hr Suite Settings", "qiwa_enabled").then(enabled => {
		if (!enabled) return;

		frm.add_custom_button(__("Verify Qiwa Contract"), function () {
			frappe.call({
				method: "hr_suite.hr_suite.integrations.qiwa.verify_contract",
				args: { employee: emp },
				freeze: true,
				freeze_message: __("Checking Qiwa…"),
				callback(r) {
					if (r.exc) return;
					const d = r.message || {};
					frappe.msgprint({
						title: __("Qiwa Contract Status"),
						message: `<b>${__("Status")}:</b> ${d.status || "—"}<br>
							<b>${__("Contract ID")}:</b> ${d.contract_id || "—"}<br>
							<b>${__("Valid Until")}:</b> ${d.expiry_date || "—"}`,
						indicator: d.status === "Active" ? "green" : "orange",
					});
					frm.reload_doc();
				},
			});
		}, __("Qiwa"));

		frm.add_custom_button(__("Nitaqat Status"), function () {
			frappe.call({
				method: "hr_suite.hr_suite.integrations.qiwa.get_nitaqat_status",
				args: { employee: emp },
				freeze: true,
				freeze_message: __("Checking Qiwa…"),
				callback(r) {
					if (r.exc) return;
					const d = r.message || {};
					frappe.msgprint({
						title: __("Nitaqat Status"),
						message: `<b>${__("Band")}:</b> ${d.band || "—"}<br>
							<b>${__("Saudization %")}:</b> ${d.saudization_pct || "—"}%`,
						indicator: "blue",
					});
				},
			});
		}, __("Qiwa"));

		frm.add_custom_button(__("Sync Log"), function () {
			frappe.set_route("List", "Government Portal Sync Log", { employee: emp, portal: "Qiwa" });
		}, __("Qiwa"));
	});

	// ── GOSI API ──
	frappe.db.get_single_value("Hr Suite Settings", "gosi_api_enabled").then(enabled => {
		if (!enabled) return;

		frm.add_custom_button(__("Register with GOSI"), function () {
			frappe.confirm(
				__("Register this employee with GOSI? This will submit their details to the GOSI portal."),
				function () {
					frappe.call({
						method: "hr_suite.hr_suite.integrations.gosi_api.register_employee",
						args: { employee: emp },
						freeze: true,
						freeze_message: __("Registering with GOSI…"),
						callback(r) {
							if (r.exc) return;
							frappe.show_alert({
								message: __(`GOSI registration submitted. Member ID: ${(r.message || {}).member_id || "—"}`),
								indicator: "green",
							});
							frm.reload_doc();
						},
					});
				}
			);
		}, __("GOSI"));

		frm.add_custom_button(__("GOSI Member Status"), function () {
			frappe.call({
				method: "hr_suite.hr_suite.integrations.gosi_api.get_employee_status",
				args: { employee: emp },
				freeze: true,
				freeze_message: __("Checking GOSI…"),
				callback(r) {
					if (r.exc) return;
					const d = r.message || {};
					frappe.msgprint({
						title: __("GOSI Member Status"),
						message: `<b>${__("Status")}:</b> ${d.status || "—"}<br>
							<b>${__("Member ID")}:</b> ${d.member_id || "—"}<br>
							<b>${__("Contribution Base")}:</b> ${d.contribution_base || "—"}`,
						indicator: d.status === "Active" ? "green" : "orange",
					});
				},
			});
		}, __("GOSI"));

		frm.add_custom_button(__("Deregister from GOSI"), function () {
			frappe.prompt(
				[
					{
						fieldname: "exit_date",
						label: __("Exit Date"),
						fieldtype: "Date",
						reqd: 1,
						default: frappe.datetime.get_today(),
					},
					{
						fieldname: "reason",
						label: __("Reason"),
						fieldtype: "Select",
						options: "Resignation\nTermination\nEnd of Contract\nDeath\nRetirement",
						reqd: 1,
					},
				],
				function (vals) {
					frappe.call({
						method: "hr_suite.hr_suite.integrations.gosi_api.deregister_employee",
						args: { employee: emp, exit_date: vals.exit_date, reason: vals.reason },
						freeze: true,
						freeze_message: __("Deregistering from GOSI…"),
						callback(r) {
							if (r.exc) return;
							frappe.show_alert({ message: __("Employee deregistered from GOSI."), indicator: "green" });
							frm.reload_doc();
						},
					});
				},
				__("Deregister from GOSI"),
				__("Submit")
			);
		}, __("GOSI"));

		frm.add_custom_button(__("Sync Log"), function () {
			frappe.set_route("List", "Government Portal Sync Log", { employee: emp, portal: "GOSI" });
		}, __("GOSI"));
	});
}

// ── UAE buttons (GPSSA / MOHRE) ───────────────────────────────────────────────

function _hr_suite_ae_buttons(frm) {
	const emp = frm.doc.name;

	frm.add_custom_button(__("GPSSA Contribution"), function () {
		frappe.set_route("List", "Statutory Contribution", { employee: emp, country_code: "AE" });
	}, __("UAE Statutory"));

	frm.add_custom_button(__("DEWS / Gratuity"), function () {
		frappe.set_route("List", "DEWS Contribution", { employee: emp });
	}, __("UAE Statutory"));

	frm.add_custom_button(__("Work Permit (UAE)"), function () {
		frappe.set_route("List", "Work Permit Iqama", { employee: emp });
	}, __("UAE Statutory"));

	frm.add_custom_button(__("Settlement Breakdown"), function () {
		_open_settlement_dialog(frm, "AE");
	}, __("UAE Statutory"));
}

// ── Bahrain buttons (SIO / Tamkeen) ──────────────────────────────────────────

function _hr_suite_bh_buttons(frm) {
	const emp = frm.doc.name;

	frm.add_custom_button(__("SIO Contribution"), function () {
		frappe.set_route("List", "Statutory Contribution", { employee: emp, country_code: "BH" });
	}, __("BH Statutory"));

	frm.add_custom_button(__("Work Permit (CPR)"), function () {
		frappe.set_route("List", "Work Permit Iqama", { employee: emp });
	}, __("BH Statutory"));

	frm.add_custom_button(__("Settlement Breakdown"), function () {
		_open_settlement_dialog(frm, "BH");
	}, __("BH Statutory"));
}

// ── India buttons (EPF / ESI / PT) ───────────────────────────────────────────

function _hr_suite_in_buttons(frm) {
	const emp = frm.doc.name;

	frm.add_custom_button(__("EPF / ESI Contribution"), function () {
		frappe.set_route("List", "EPF ESI Contribution", { employee: emp });
	}, __("IN Statutory"));

	frm.add_custom_button(__("Professional Tax"), function () {
		frappe.set_route("List", "Professional Tax", { employee: emp });
	}, __("IN Statutory"));

	frm.add_custom_button(__("Gratuity Estimate"), function () {
		_open_settlement_dialog(frm, "IN");
	}, __("IN Statutory"));
}

// ── Oman buttons (PASI) ────────────────────────────────────────────────────────

function _hr_suite_om_buttons(frm) {
	const emp = frm.doc.name;

	frm.add_custom_button(__("PASI Contribution"), function () {
		frappe.set_route("List", "Statutory Contribution", { employee: emp, country_code: "OM" });
	}, __("OM Statutory"));

	frm.add_custom_button(__("Work Permit (Oman)"), function () {
		frappe.set_route("List", "Work Permit Iqama", { employee: emp });
	}, __("OM Statutory"));

	frm.add_custom_button(__("Settlement Breakdown"), function () {
		_open_settlement_dialog(frm, "OM");
	}, __("OM Statutory"));
}

// ── Shared settlement dialog (non-SA countries) ───────────────────────────────

function _open_settlement_dialog(frm, country) {
	frappe.prompt(
		[
			{
				fieldname: "termination_reason",
				label: __("Termination Reason"),
				fieldtype: "Select",
				options: [
					"Resignation by Employee",
					"Termination by Employer",
					"End of Contract",
					"Retirement",
					"Death",
				].join("\n"),
				reqd: 1,
				default: "Resignation by Employee",
			},
			{
				fieldname: "termination_date",
				label: __("As Of Date"),
				fieldtype: "Date",
				default: frappe.datetime.get_today(),
			},
		],
		function (values) {
			frappe.call({
				method: "hr_suite.hr_suite.utils.get_settlement_estimate",
				args: {
					employee: frm.doc.name,
					termination_reason: values.termination_reason,
					termination_date: values.termination_date || frappe.datetime.get_today(),
				},
				callback: function (r) {
					if (!r.message) return;
					let d = r.message;
					frappe.msgprint({
						title: __("Settlement Estimate"),
						message: `<table class="table table-condensed" style="margin-top:8px">
							<tr><td>${__("Formula")}</td><td><b>${d.formula || country}</b></td></tr>
							<tr><td>${__("Years of Service")}</td><td><b>${flt(d.years_of_service, 2)}</b></td></tr>
							<tr><td>${__("Basic Salary")}</td><td><b>${format_currency(d.basic_salary)}</b></td></tr>
							<tr><td>${__("Gross Entitlement")}</td><td><b>${format_currency(d.gross_entitlement)}</b></td></tr>
							<tr><td>${__("Factor")}</td><td>${d.factor_label || ""}</td></tr>
							<tr><td>${__("Net Entitlement")}</td><td><b>${format_currency(d.net_entitlement)}</b></td></tr>
						</table>
						<small class="text-muted">${d.notes || ""}</small>`,
						indicator: "blue",
					});
				},
			});
		},
		__("Settlement Estimate"),
		__("Calculate")
	);
}

// ── Dashboard alerts — country-aware document expiry ─────────────────────────

function _hr_suite_document_alerts(frm) {
	frappe.db
		.get_list("Work Permit Iqama", {
			filters: { employee: frm.doc.name },
			fields: [
				"permit_type",
				"iqama_expiry_date",
				"work_permit_expiry_date",
				"exit_reentry_expiry_date",
			],
			limit: 1,
		})
		.then(function (docs) {
			if (!docs || !docs.length) return;
			const today = frappe.datetime.get_today();
			const rec = docs[0];
			const checks = [
				{ label: rec.permit_type || __("Residence Permit"), date: rec.iqama_expiry_date },
				{ label: __("Work Permit"), date: rec.work_permit_expiry_date },
				{ label: __("Exit / Re-entry Visa"), date: rec.exit_reentry_expiry_date },
			];
			checks.forEach(function (item) {
				if (!item.date) return;
				const days = frappe.datetime.get_diff(item.date, today);
				if (days <= 0) {
					frm.dashboard.add_comment(
						__("{0} EXPIRED on {1}", [item.label, item.date]),
						"red", true
					);
				} else if (days <= 30) {
					frm.dashboard.add_comment(
						__("{0} expires in {1} days ({2})", [item.label, days, item.date]),
						"orange", true
					);
				} else if (days <= 90) {
					frm.dashboard.add_comment(
						__("{0} expires in {1} days ({2})", [item.label, days, item.date]),
						"yellow", true
					);
				}
			});
		});
}

// ── Dashboard contract banner — works for Country Employment Contract ─────────

function _hr_suite_contract_banner(frm) {
	// Try Country Employment Contract first (multi-country)
	frappe.db
		.get_list("Country Employment Contract", {
			filters: { employee: frm.doc.name, contract_status: "Active" },
			fields: [
				"name", "basic_salary", "housing_allowance", "transport_allowance",
				"total_salary", "probation_end_date", "contract_type", "work_country", "currency",
			],
			limit: 1,
		})
		.then(function (contracts) {
			if (contracts && contracts.length) {
				const c = contracts[0];
				const prob = c.probation_end_date
					? ` &nbsp;|&nbsp; ${__("Probation ends")}: <b>${c.probation_end_date}</b>`
					: "";
				const flag = c.work_country ? ` [${c.work_country}]` : "";
				const empType = frm.doc.hr_suite_employee_type
					? ` &nbsp;|&nbsp; <b>${frm.doc.hr_suite_employee_type}</b>`
					: "";
				frm.dashboard.add_comment(
					`<b>${__("Active Contract")}${flag}:</b> ${c.contract_type || ""}${empType}
					 &nbsp;|&nbsp; ${__("Basic")}: <b>${format_currency(c.basic_salary, c.currency)}</b>
					 &nbsp;|&nbsp; ${__("Total")}: <b>${format_currency(c.total_salary, c.currency)}</b>${prob}`,
					"blue", true
				);
				return;
			}
			// Fallback: Saudi Employment Contract (legacy)
			frappe.db
				.get_list("Saudi Employment Contract", {
					filters: { employee: frm.doc.name, contract_status: "Active" },
					fields: [
						"name", "basic_salary", "housing_allowance", "transport_allowance",
						"total_salary", "probation_end_date", "contract_type",
					],
					limit: 1,
				})
				.then(function (saContracts) {
					if (!saContracts || !saContracts.length) return;
					const c = saContracts[0];
					const prob = c.probation_end_date
						? ` &nbsp;|&nbsp; ${__("Probation ends")}: <b>${c.probation_end_date}</b>`
						: "";
					const empType = frm.doc.hr_suite_employee_type
						? ` &nbsp;|&nbsp; <b>${frm.doc.hr_suite_employee_type}</b>`
						: "";
					frm.dashboard.add_comment(
						`<b>${__("Active Contract")} [SA]:</b> ${c.contract_type || ""}${empType}
						 &nbsp;|&nbsp; ${__("Basic")}: <b>${format_currency(c.basic_salary)}</b>
						 &nbsp;|&nbsp; ${__("Total")}: <b>${format_currency(c.total_salary)}</b>${prob}`,
						"blue", true
					);
				});
		});
}

// ── Onboarding banner ─────────────────────────────────────────────────────────

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
			const r = rows[0];
			frm.dashboard.add_comment(
				`${__("Onboarding")} ${r.status}: <b>${r.completion_percentage}%</b> complete
				 — <a href="/app/employee-onboarding/${r.name}">${r.name}</a>`,
				"orange", true
			);
		});
}
