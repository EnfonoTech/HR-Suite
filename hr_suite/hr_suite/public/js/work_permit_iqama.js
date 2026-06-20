// HR Suite — Work Permit / Iqama form: Muqeem live verification

frappe.ui.form.on("Work Permit / Iqama", {
	refresh(frm) {
		if (frm.is_new()) return;

		frappe.db.get_value("Hr Suite Settings", null, ["muqeem_enabled", "qiwa_enabled"])
			.then(r => {
				const s = r.message || {};

				if (s.muqeem_enabled) {
					frm.add_custom_button(__("Verify Iqama (Muqeem)"), function () {
						if (!frm.doc.iqama_number) {
							frappe.msgprint(__("Enter an Iqama Number first."));
							return;
						}
						frappe.show_progress(__("Contacting Muqeem…"), 0, 100);
						frappe.call({
							method: "hr_suite.hr_suite.integrations.muqeem.verify_iqama",
							args: {
								iqama_number: frm.doc.iqama_number,
								employee: frm.doc.employee,
							},
							callback(res) {
								frappe.hide_progress();
								if (res.exc) return;
								frappe.show_alert({ message: __("Iqama verified from Muqeem — record updated."), indicator: "green" });
								frm.reload_doc();
							},
						});
					}, __("Muqeem"));

					frm.add_custom_button(__("Exit Re-entry Status"), function () {
						if (!frm.doc.iqama_number) {
							frappe.msgprint(__("Enter an Iqama Number first."));
							return;
						}
						frappe.call({
							method: "hr_suite.hr_suite.integrations.muqeem.get_exit_reentry",
							args: {
								iqama_number: frm.doc.iqama_number,
								employee: frm.doc.employee,
							},
							callback(res) {
								if (res.exc) return;
								const d = res.message || {};
								frappe.msgprint({
									title: __("Exit Re-entry — Muqeem"),
									message: `<table class="table table-bordered table-sm" style="font-size:13px;">
										<tr><td><b>Visa No.</b></td><td>${d.visa_number || "—"}</td></tr>
										<tr><td><b>Expiry</b></td><td>${d.expiry_date || "—"}</td></tr>
										<tr><td><b>Status</b></td><td>${d.status || "—"}</td></tr>
									</table>`,
									indicator: "blue",
								});
								frm.reload_doc();
							},
						});
					}, __("Muqeem"));

					if (frm.doc.employee) {
						frm.add_custom_button(__("Initiate Final Exit"), function () {
							frappe.prompt(
								[{ label: __("Exit Date"), fieldname: "exit_date", fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() }],
								function(vals) {
									frappe.confirm(
										__("This will submit a Final Exit request to Muqeem for this employee. Continue?"),
										function() {
											frappe.call({
												method: "hr_suite.hr_suite.integrations.muqeem.initiate_final_exit",
												args: {
													iqama_number: frm.doc.iqama_number,
													exit_date: vals.exit_date,
													employee: frm.doc.employee,
												},
												callback(res) {
													if (res.exc) return;
													frappe.show_alert({ message: __("Final exit request submitted to Muqeem."), indicator: "green" });
												},
											});
										}
									);
								},
								__("Initiate Final Exit"), __("Submit to Muqeem")
							);
						}, __("Muqeem"));
					}
				}

				if (s.qiwa_enabled && frm.doc.employee) {
					frm.add_custom_button(__("Verify Wathiqa Contract"), function () {
						frappe.show_progress(__("Contacting Qiwa…"), 0, 100);
						frappe.call({
							method: "hr_suite.hr_suite.integrations.qiwa.verify_contract",
							args: {
								iqama_number: frm.doc.iqama_number,
								employee: frm.doc.employee,
							},
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
										<tr><td><b>Verified</b></td><td>${d.is_verified ? "✅ Yes" : "❌ No"}</td></tr>
									</table>`,
									indicator: d.is_verified ? "green" : "orange",
								});
							},
						});
					}, __("Qiwa"));
				}

				// Sync log shortcut
				if (s.muqeem_enabled || s.qiwa_enabled) {
					frm.add_custom_button(__("View Sync Logs"), function () {
						frappe.set_route("List", "Government Portal Sync Log", {
							employee: frm.doc.employee,
						});
					});
				}
			});
	},
});
