// HR Suite — Payroll Preview
// Read-only review screen. It never posts and never stores a salary figure of its own;
// every button here either re-reads the source documents or hands off to Payroll Entry.

frappe.ui.form.on("Payroll Preview", {
	setup(frm) {
		set_payroll_preview_indicators();

		frm.set_query("branch", () => ({ filters: { company: frm.doc.company } }));
		frm.set_query("department", () => ({ filters: { company: frm.doc.company } }));
	},

	refresh(frm) {
		apply_payroll_preview_section_descriptions(frm);
		render_payroll_preview_status(frm);
		add_payroll_preview_buttons(frm);
	},

	company(frm) {
		frm.set_value("branch", null);
		frm.set_value("department", null);
		set_currency_from_company(frm);
	},

	payroll_frequency(frm) {
		set_period_end_date(frm);
	},

	start_date(frm) {
		set_period_end_date(frm);
	},
});

// ── buttons ──────────────────────────────────────────────────────────────────

function add_payroll_preview_buttons(frm) {
	if (frm.is_new()) return;

	frm.clear_custom_buttons();

	frm.add_custom_button(__("Refresh Allocations"), async () => {
		// Save first: refresh_allocations calls save() server-side, which would trip the
		// modified-timestamp check if the client still held unsaved changes.
		if (frm.is_dirty()) await frm.save();

		frappe.dom.freeze(__("Reading the source documents..."));
		try {
			await frm.call("refresh_allocations");
			await frm.reload_doc();
			frappe.show_alert({
				message: __("Allocations refreshed"),
				indicator: "green",
			});
		} finally {
			frappe.dom.unfreeze();
		}
	}).addClass("btn-primary");

	if (!frm.doc.employees || !frm.doc.employees.length) return;

	// Hidden while anything is still blocking — make_payroll_entry refuses anyway,
	// but the button should not invite a call that cannot succeed.
	if (cint(frm.doc.employees_with_issues) > 0) return;

	frm.add_custom_button(__("Create Payroll Entry"), () => {
		frappe.model.open_mapped_doc({
			method: "hr_suite.hr_suite.doctype.payroll_preview.payroll_preview.make_payroll_entry",
			frm: frm,
		});
	});
}

// ── presentation ─────────────────────────────────────────────────────────────

function render_payroll_preview_status(frm) {
	frm.dashboard.clear_headline();

	if (frm.is_new() || !frm.doc.last_refreshed_on) {
		frm.dashboard.set_headline(
			__("Save, then click {0} to read every allocation booked for this period.", [
				`<b>${__("Refresh Allocations")}</b>`,
			]),
			"blue"
		);
		return;
	}

	const issues = cint(frm.doc.employees_with_issues);
	const employees = cint(frm.doc.number_of_employees);

	if (issues > 0) {
		frm.dashboard.set_headline(
			__("{0} of {1} employee(s) have blocking issues. Resolve them, refresh, then create the Payroll Entry.", [
				issues,
				employees,
			]),
			"red"
		);
	} else {
		frm.dashboard.set_headline(
			__("{0} employee(s) ready. No blocking issues found as of {1}.", [
				employees,
				frappe.datetime.str_to_user(frm.doc.last_refreshed_on),
			]),
			"green"
		);
	}
}

function set_payroll_preview_indicators() {
	// Addressed explicitly rather than through frm.set_indicator_formatter, because
	// `employee` exists on BOTH child tables and the helper resolves only the first.
	const employee_row = frappe.meta.docfield_map["Payroll Preview Employee"];
	if (employee_row && employee_row.employee) {
		employee_row.employee.formatter = function (value, df, options, doc) {
			if (!value) return value;
			const indicator = doc && cint(doc.has_issues) ? "red" : "green";
			return `<a class="indicator ${indicator}">${frappe.utils.escape_html(value)}</a>`;
		};
	}

	const allocation_row = frappe.meta.docfield_map["Payroll Preview Allocation"];
	if (allocation_row && allocation_row.entry_type) {
		allocation_row.entry_type.formatter = function (value) {
			if (!value) return value;
			const colours = { Earning: "green", Deduction: "orange", Information: "blue" };
			const indicator = colours[value] || "gray";
			return `<span class="indicator ${indicator}">${__(value)}</span>`;
		};
	}
}

function apply_payroll_preview_section_descriptions(frm) {
	// Built inside the function so every string is a literal argument to __() and stays
	// extractable for translation.
	const descriptions = {
		filters_section: __("Narrow the employee set. These filters are carried across to the Payroll Entry."),
		summary_section: __(
			"Totals are the sum of the employee rows below, which are themselves reads of the source documents."
		),
		allocations_section: __(
			"Every item already booked against an employee for this period, with the document it came from."
		),
	};

	Object.entries(descriptions).forEach(([fieldname, description]) => {
		const field = frm.get_field(fieldname);
		if (field && field.df) {
			field.df.description = description;
			field.refresh();
		}
	});
}

// ── period helpers ───────────────────────────────────────────────────────────

function set_currency_from_company(frm) {
	if (!frm.doc.company) return;

	frappe.db.get_value("Company", frm.doc.company, "default_currency").then((r) => {
		if (r && r.message) frm.set_value("currency", r.message.default_currency);
	});
}

function set_period_end_date(frm) {
	if (!frm.doc.start_date || !frm.doc.payroll_frequency) return;

	// Reuses the same helper Payroll Entry uses, so the two screens agree on the period.
	frappe.call({
		method: "hrms.payroll.doctype.payroll_entry.payroll_entry.get_start_end_dates",
		args: {
			payroll_frequency: frm.doc.payroll_frequency,
			start_date: frm.doc.start_date,
			company: frm.doc.company,
		},
		callback(r) {
			if (!r || !r.message) return;
			frm.set_value("start_date", r.message.start_date);
			frm.set_value("end_date", r.message.end_date);
		},
	});
}
