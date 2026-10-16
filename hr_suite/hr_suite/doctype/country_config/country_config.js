// HR Suite: Country Config. Run the leave accrual by hand, so a country just switched onto the
// HR Suite Ledger can be checked without waiting for the 1st of the month.
frappe.ui.form.on("Country Config", {
	refresh: function (frm) {
		if (frm.is_new() || frm.doc.leave_accrual_engine !== "HR Suite Ledger") return;
		if (!frappe.user.has_role("HR Manager") && !frappe.user.has_role("System Manager")) return;

		frm.add_custom_button(__("Run Accrual Now"), function () {
			frappe.confirm(
				__("Accrue every month still owed, up to the end of last month, for all employees of countries on the HR Suite Ledger. Months already accrued are skipped, so this is safe to repeat."),
				function () {
					frappe.call({
						method: "hr_suite.hr_suite.leave_accrual.run_accrual",
						freeze: true,
						callback: function (r) {
							const out = r.message || {};
							let html = __("{0} employee(s) accrued, {1} ledger row(s) written.", [out.employees || 0, out.rows || 0]);
							if ((out.failed || []).length) html += "<br>" + __("Failed (see Error Log): {0}", [out.failed.join(", ")]);
							const legacy = out.legacy_allocations || [];
							if (legacy.length) {
								html += "<br><br><b>" + __("Annual leave allocated outside the ledger") + "</b><br>"
									+ __("These add to the accrued balance. Cancel them, or fold them into the opening balance:") + "<ul>"
									+ legacy.map((l) => `<li>${l.employee}: ${l.days} ${__("days")} (${l.allocation})</li>`).join("") + "</ul>";
							}
							frappe.msgprint({ title: __("Leave Accrual"), message: html, indicator: legacy.length ? "orange" : "green" });
						},
					});
				}
			);
		}, __("Actions"));
	},
});
