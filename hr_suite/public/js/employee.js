frappe.ui.form.on("Employee", {
	refresh(frm) {
		render_paid_payroll_history(frm);
	},
});

function render_paid_payroll_history(frm) {
	const field = frm.get_field("salary_mode");
	if (!field || !field.$wrapper || frm.is_new()) {
		return;
	}

	const $section = get_paid_payroll_section(field.$wrapper);
	if (!$section.length) {
		return;
	}

	$section.html(`<div class="text-muted small">${__("Loading paid payroll history...")}</div>`);

	frappe.call({
		method: "hr_suite.hr_suite.api.get_employee_paid_payroll_history",
		args: {
			employee: frm.doc.name,
			limit: 12,
		},
		callback: ({ message }) => {
			const rows = Array.isArray(message) ? message : [];
			$section.html(build_paid_payroll_history_html(rows));
		},
		error: () => {
			$section.html(
				`<div class="text-danger small">${__("Unable to load paid payroll history right now.")}</div>`
			);
		},
	});
}

function get_paid_payroll_section($fieldWrapper) {
	const $sectionBody = $fieldWrapper.closest(".section-body");
	if (!$sectionBody.length) {
		return $();
	}

	let $section = $sectionBody.find(".employee-paid-payroll-history");

	if ($section.length) {
		return $section.find(".employee-paid-payroll-history-body");
	}

	$section = $(
		`<div class="employee-paid-payroll-history" style="margin-top: 24px;">
			<div class="form-dashboard-section">
				<div style="display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px;">
					<h5 style="margin:0;">${__("Paid Payroll History")}</h5>
				</div>
				<div class="employee-paid-payroll-history-body"></div>
			</div>
		</div>`
	);

	$sectionBody.append($section);
	return $section.find(".employee-paid-payroll-history-body");
}

function build_paid_payroll_history_html(rows) {
	if (!rows.length) {
		return `<div class="text-muted small">${__("No paid payroll records were found for this employee.")}</div>`;
	}

	const tableRows = rows
		.map((row) => {
			const payrollLink = frappe.utils.get_form_link("Saudi Monthly Payroll", row.payroll, true);
			const journalLink = row.journal_entry
				? frappe.utils.get_form_link("Journal Entry", row.journal_entry, true)
				: '<span class="text-muted">-</span>';
			const postingDate = row.posting_date
				? frappe.datetime.str_to_user(row.posting_date)
				: "-";
			const salaryMode = frappe.utils.escape_html(row.salary_mode || "-");
			return `
				<tr>
					<td>${payrollLink}<div class="text-muted small">${frappe.utils.escape_html(row.period_label || "-")}</div></td>
					<td>${postingDate}</td>
					<td>${format_currency(row.net_salary)}</td>
					<td>${format_currency(row.gross_salary)}</td>
					<td>${format_currency(row.total_deductions)}</td>
					<td>${salaryMode}</td>
					<td>${journalLink}</td>
				</tr>`;
		})
		.join("");

	return `
		<div class="table-responsive">
			<table class="table table-bordered" style="margin-bottom: 0;">
				<thead>
					<tr>
						<th>${__("Payroll")}</th>
						<th>${__("Posting Date")}</th>
						<th>${__("Net Salary")}</th>
						<th>${__("Gross Salary")}</th>
						<th>${__("Deductions")}</th>
						<th>${__("Salary Mode")}</th>
						<th>${__("Journal Entry")}</th>
					</tr>
				</thead>
				<tbody>${tableRows}</tbody>
			</table>
		</div>`;
}