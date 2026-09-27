// Copyright (c) 2026, Enfono Technologies and contributors
// For license information, please see license.txt

// The whole point of this form is that somebody can look at a number that was paid out
// mid-month and see WHY it is that number. The grid of computed lines is accurate but
// unreadable, so the breakdown below re-states it as three lists: what was earned, what
// was taken off, and what was deliberately left alone because payroll already has it.

frappe.ui.form.on("Salary Settlement", {
	onload(frm) {
		if (frm.is_new() && !frm.doc.settlement_date) {
			frm.set_value("settlement_date", frappe.datetime.get_today());
		}
	},

	refresh(frm) {
		render_breakdown(frm);
		add_links(frm);
		add_payment_advice_button(frm);

		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			frm.add_custom_button(__("Recalculate"), () => frm.save());
		}
	},

	employee(frm) {
		if (!frm.doc.employee) return;

		frappe.call({
			method:
				"hr_suite.hr_suite.doctype.salary_settlement.salary_settlement.get_settlement_defaults",
			args: {
				employee: frm.doc.employee,
				settlement_date: frm.doc.settlement_date || frappe.datetime.get_today(),
			},
			callback(r) {
				if (!r.message) return;

				if (!frm.doc.period_from) frm.set_value("period_from", r.message.period_from);
				if (!frm.doc.period_to) frm.set_value("period_to", r.message.period_to);
				if (r.message.currency) frm.set_value("currency", r.message.currency);

				if (!r.message.has_salary_structure) {
					// Saying it here rather than only on save: the settlement cannot be
					// computed at all without an assignment, and finding that out after
					// filling the whole form is a wasted trip.
					frm.dashboard.clear_comment();
					frm.dashboard.add_comment(
						__("{0} has no submitted Salary Structure Assignment, so nothing can be settled.", [
							frappe.utils.escape_html(frm.doc.employee_name || frm.doc.employee),
						]),
						"red",
						true
					);
				}
			},
		});
	},

	settlement_date(frm) {
		if (frm.doc.settlement_date && !frm.doc.period_to) {
			frm.set_value("period_to", frm.doc.settlement_date);
		}
	},

	lines(frm) {
		render_breakdown(frm);
	},
});

function add_links(frm) {
	if (frm.doc.journal_entry) {
		frm.add_custom_button(
			__("Journal Entry"),
			() => frappe.set_route("Form", "Journal Entry", frm.doc.journal_entry),
			__("View")
		);
	}

	if (frm.doc.annual_leave_disbursement) {
		frm.add_custom_button(
			__("Leave Disbursement"),
			() =>
				frappe.set_route(
					"Form",
					"Annual Leave Disbursement",
					frm.doc.annual_leave_disbursement
				),
			__("View")
		);
	}

	if (frm.doc.docstatus === 1) {
		frm.add_custom_button(
			__("Payroll Recoveries"),
			() =>
				frappe.set_route("List", "Additional Salary", {
					ref_doctype: "Salary Settlement",
					ref_docname: frm.doc.name,
				}),
			__("View")
		);
	}
}

function money(frm, value) {
	return frappe.format(
		flt(value),
		{ fieldtype: "Currency", options: "currency" },
		{ inline: 1 },
		frm.doc
	);
}

function render_breakdown(frm) {
	const field = frm.get_field("settlement_breakdown");
	if (!field) return;

	const lines = frm.doc.lines || [];
	if (!lines.length) {
		field.$wrapper.html(
			`<p class="text-muted">${__("Save the settlement to work out what is owed.")}</p>`
		);
		return;
	}

	const earnings = lines.filter((row) => row.entry_type === "Earning");
	const deductions = lines.filter((row) => row.entry_type === "Deduction");
	const information = lines.filter((row) => row.entry_type === "Information");

	let html = '<div class="salary-settlement-breakdown">';

	html += section(
		frm,
		__("Earned and payable"),
		earnings,
		"green",
		__("Nothing was earned in this period.")
	);
	html += section(
		frm,
		__("Recovered from this settlement"),
		deductions,
		"red",
		__("Nothing owed that payroll will not already collect.")
	);

	html += `
		<div style="margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--border-color);">
			${total_row(__("Earned Salary"), money(frm, frm.doc.earned_amount))}
			${
				flt(frm.doc.leave_salary_amount)
					? total_row(__("Leave Salary"), money(frm, frm.doc.leave_salary_amount))
					: ""
			}
			${total_row(__("Total Deductions"), "- " + money(frm, frm.doc.total_deductions))}
			${total_row(__("Net Payable"), money(frm, frm.doc.net_payable), true)}
		</div>`;

	if (frm.doc.proration_basis) {
		html += `
			<div class="text-muted" style="margin-top: 10px; font-size: var(--text-sm); white-space: pre-line;">
				${frappe.utils.escape_html(frm.doc.proration_basis)}
			</div>`;
	}

	if (information.length) {
		// Collapsed, because these rows change no figure on this document. They are here
		// so nobody adds them by hand after noticing they are "missing" from the net —
		// the month's own payslip carries every one of them.
		html += `
			<details style="margin-top: 12px;">
				<summary class="text-muted" style="cursor: pointer;">
					${__("{0} item(s) payroll already carries", [information.length])}
				</summary>
				${section(frm, "", information, "gray", "")}
			</details>`;
	}

	html += "</div>";
	field.$wrapper.html(html);
}

function section(frm, title, rows, indicator, empty_message) {
	if (!rows.length) {
		return empty_message
			? `<p class="text-muted" style="margin-top: 8px;">${empty_message}</p>`
			: "";
	}

	let html = title
		? `<div style="margin-top: 12px;"><span class="indicator-pill ${indicator}">${title}</span></div>`
		: "";

	html += '<table class="table table-bordered" style="margin-top: 8px;"><tbody>';
	for (const row of rows) {
		const label =
			row.salary_component ||
			[row.source_doctype, row.source_name].filter(Boolean).join(" ") ||
			__("Item");
		const amount = row.entry_type === "Information" ? row.amount : row.payable_amount;

		html += `
			<tr>
				<td style="width: 30%;">${frappe.utils.escape_html(label)}</td>
				<td class="text-muted" style="width: 50%; font-size: var(--text-sm);">
					${frappe.utils.escape_html(row.description || "")}
				</td>
				<td class="text-right" style="width: 20%;">${money(frm, amount)}</td>
			</tr>`;
	}
	html += "</tbody></table>";

	return html;
}

function total_row(label, value, bold) {
	const weight = bold ? "font-weight: 600;" : "";
	return `
		<div style="display: flex; justify-content: space-between; padding: 2px 0; ${weight}">
			<span>${label}</span><span>${value}</span>
		</div>`;
}

// Ask finance to pay this document. Deliberately a button and not an on_submit hook:
// raising (and submitting) a second submittable document inside another document's
// submit transaction is how a payroll run died here once — anything the advice refuses
// would roll the source document back with it.
function add_payment_advice_button(frm) {
	if (frm.doc.docstatus !== 1) return;

	frm.add_custom_button(__("Raise Payment Advice"), function () {
		frappe.call({
			method: "hr_suite.hr_suite.payment_advice.raise_for_document",
			args: { doctype: frm.doc.doctype, name: frm.doc.name },
			freeze: true,
			freeze_message: __("Raising payment advice..."),
			callback(r) {
				if (!r.message) return;
				frappe.show_alert({
					message: r.message.created
						? __("Payment Advice {0} raised.", [r.message.advice])
						: __("Payment Advice {0} was already raised for this document.", [r.message.advice]),
					indicator: "green",
				});
				frappe.set_route("Form", "HR Payment Advice", r.message.advice);
			},
		});
	}, __("Actions"));
}
