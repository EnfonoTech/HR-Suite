// HR Suite: review and confirm an employee's gratuity at exit (SFT reply, section 10).
// Shows provided to date, the final gratuity for the exit reason, the difference and anything pending; on
// Confirm, the Gratuity Finalisation is submitted: only the difference is posted and an HR Payment Advice raised.
frappe.pages["gratuity-finalisation"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Gratuity Finalisation"), single_column: true });
	const body = $(`<div class="hrs-gf" style="max-width:900px"></div>`).appendTo(page.main);
	const employee = page.add_field({
		fieldname: "employee",
		label: __("Employee"),
		fieldtype: "Link",
		options: "Employee",
		get_query: () => ({ filters: { relieving_date: ["is", "set"] } }),
		change: () => load(),
	});
	const reason = page.add_field({
		fieldname: "exit_reason",
		label: __("Exit Reason"),
		fieldtype: "Select",
		options: ["Termination", "End of Contract", "Resignation", "Dismissal"],
		default: "Termination",
		change: () => load(),
	});
	if (frappe.route_options && frappe.route_options.employee) {
		employee.set_value(frappe.route_options.employee);
		frappe.route_options = null;
	}
	body.html(`<p class="text-muted">${__("Choose an employee who has a Relieving Date.")}</p>`);

	function load() {
		const emp = employee.get_value();
		if (!emp) return;
		frappe.call({
			method: "hr_suite.hr_suite.doctype.gratuity_finalisation.gratuity_finalisation.preview",
			args: { employee: emp, exit_reason: reason.get_value() || "Termination" },
			freeze: true,
			callback: (r) => r.message && render(r.message),
		});
	}

	function render(d) {
		const esc = (v) => frappe.utils.escape_html(v == null ? "" : String(v));
		const money = (v) => format_currency(v, frappe.defaults.get_default("currency"));
		const diff = Number(d.difference || 0);
		const row = (k, v) => `<tr><td class="text-muted" style="width:40%">${k}</td><td>${v}</td></tr>`;
		const done = d.existing && d.existing.docstatus === 1;
		body.html(`
			<table class="table table-bordered">
				${row(__("Employee"), `${esc(d.employee)}: ${esc(d.employee_name)}`)}
				${row(__("Company"), esc(d.company))}
				${row(__("Joined / Relieved"), `${frappe.datetime.str_to_user(d.date_of_joining)} / ${frappe.datetime.str_to_user(d.relieving_date)} (${esc(d.years_of_service)} ${__("years")})`)}
				${row(__("Provided To Date"), money(d.accrued_to_date))}
				${row(__("Final Gratuity"), `<b>${money(d.final_amount)}</b>`)}
				${row(__("Difference To Post"), `<b>${money(diff)}</b> ${diff < 0 ? `<span class="text-muted">(${__("excess provision reversed")})</span>` : ""}`)}
			</table>
			<h6>${__("Calculation")}</h6><pre style="white-space:pre-wrap">${esc(d.calculation_notes)}</pre>
			<h6>${__("Pending Items")}</h6><pre style="white-space:pre-wrap">${esc(d.pending_items)}</pre>
			${d.accounts_error ? `<div class="alert alert-danger">${esc(d.accounts_error)}</div>` : ""}
			${done ? `<div class="alert alert-info">${__("Already finalised in {0}.", [`<a href="/app/gratuity-finalisation/${encodeURIComponent(d.existing.name)}">${esc(d.existing.name)}</a>`])}</div>` : ""}
			<button class="btn btn-primary btn-confirm" ${done || d.accounts_error ? "disabled" : ""}>${__("Confirm And Post")}</button>`);
		body.find(".btn-confirm").on("click", () => confirm_post(d));
	}

	function confirm_post(d) {
		frappe.confirm(
			__("Post the difference of {0} for {1} and raise the HR Payment Advice for {2}?", [
				format_currency(d.difference), frappe.utils.escape_html(d.employee_name || d.employee), format_currency(d.final_amount),
			]),
			() =>
				frappe.call({
					method: "hr_suite.hr_suite.doctype.gratuity_finalisation.gratuity_finalisation.confirm",
					args: { employee: d.employee, exit_reason: d.exit_reason },
					freeze: true,
					callback: (r) => r.message && frappe.set_route("Form", "Gratuity Finalisation", r.message),
				})
		);
	}
};
