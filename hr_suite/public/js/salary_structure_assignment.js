// HR Suite — Salary Component Override buttons on Salary Structure Assignment

frappe.ui.form.on("Salary Structure Assignment", {
	refresh(frm) {
		if (frm.is_new()) return;
		_inject_override_buttons(frm);
		frm.add_custom_button(__("Apply Salary Breakup"), () => _show_breakup_dialog(frm));
	},
	after_save(frm) {
		_inject_override_buttons(frm);
	},
});

// ── Apply Salary Breakup ────────────────────────────────────────────────────

function _show_breakup_dialog(frm) {
	const today = frappe.datetime.get_today();
	let _preview_timer = null;

	const d = new frappe.ui.Dialog({
		title: __("Apply Salary Breakup"),
		fields: [
			{
				fieldname: "total_salary",
				fieldtype: "Currency",
				label: __("Total Salary"),
				reqd: 1,
				description: __("Applies the nearest band at or below this amount from the Salary Breakup Table."),
				onchange() {
					clearTimeout(_preview_timer);
					_preview_timer = setTimeout(() => _load_preview(d, frm), 400);
				},
			},
			{ fieldtype: "Column Break" },
			{
				fieldname: "effective_date",
				fieldtype: "Date",
				label: __("Effective From"),
				reqd: 1,
				default: today,
				description: __("Past/today → applied immediately. Future → scheduled."),
			},
			{ fieldtype: "Section Break" },
			{
				fieldname: "breakup_preview",
				fieldtype: "HTML",
				options: `<div id="breakup-preview-area" style="min-height:28px;"></div>`,
			},
			{ fieldtype: "Section Break" },
			{
				fieldname: "notes",
				fieldtype: "Small Text",
				label: __("Notes (optional)"),
			},
		],
		primary_action_label: __("Apply"),
		primary_action(values) {
			d.disable_primary_action();

			frappe.call({
				method: "hr_suite.hr_suite.salary_override_api.apply_salary_breakup",
				args: {
					employee: frm.doc.employee,
					salary_structure_assignment: frm.doc.name,
					total_salary: values.total_salary,
					effective_date: values.effective_date,
					notes: values.notes || "",
				},
				callback(r) {
					if (r.exc) {
						d.enable_primary_action();
						return;
					}
					const result = r.message || {};
					d.hide();

					const all_applied = (result.results || []).every(row => row.status === "Applied");
					if (all_applied) {
						frm.reload_doc();
						frappe.show_alert({
							message: __("Salary breakup applied for Total Salary {0}.", [
								frappe.format(values.total_salary, { fieldtype: "Currency" }),
							]),
							indicator: "green",
						});
					} else {
						frappe.show_alert({
							message: __("Salary breakup scheduled for {0}.", [
								frappe.format(values.effective_date, { fieldtype: "Date" }),
							]),
							indicator: "blue",
						});
					}
				},
				error() {
					d.enable_primary_action();
				},
			});
		},
	});

	d.show();
}

function _load_preview(d, frm) {
	const total_salary = d.get_value("total_salary");
	const $area = d.$body.find("#breakup-preview-area");

	if (!total_salary || total_salary <= 0) {
		$area.empty();
		return;
	}

	$area.html(`<span style="color:#8d99a6;font-size:12px;">${__("Loading preview…")}</span>`);

	frappe.call({
		method: "hr_suite.hr_suite.doctype.salary_breakup_table.salary_breakup_table.get_breakup_preview",
		args: { employee: frm.doc.employee, total_salary },
		callback(r) {
			const b = r.message;
			if (!b) {
				$area.html(`<span style="color:#e74c3c;font-size:12px;">⚠ ${__("No breakup band found for this amount.")}</span>`);
				return;
			}

			const fmt = v => frappe.format(v, { fieldtype: "Currency" });
			const isExact = flt(b.matched_total) === flt(total_salary);
			const bandNote = isExact
				? `<span style="color:#27ae60;">✓ ${__("Exact match")}</span>`
				: `<span style="color:#e67e22;">↓ ${__("Using band:")} <b>${fmt(b.matched_total)}</b></span>`;

			$area.html(`
				<div style="background:#f8f9fa;border:1px solid #e2e6ea;border-radius:4px;padding:10px 12px;font-size:12px;">
					<div style="margin-bottom:6px;">${bandNote}</div>
					<table style="width:100%;border-collapse:collapse;">
						<tr>
							<td style="padding:2px 8px 2px 0;color:#6c757d;">${__("Basic")}</td>
							<td style="text-align:right;font-weight:600;font-family:monospace;">${fmt(b.basic)}</td>
							<td style="padding:2px 0 2px 16px;color:#6c757d;">${__("HRA / Living")}</td>
							<td style="text-align:right;font-weight:600;font-family:monospace;">${fmt(b.hra)}</td>
						</tr>
						<tr>
							<td style="padding:2px 8px 2px 0;color:#6c757d;">${__("Transport / Food")}</td>
							<td style="text-align:right;font-weight:600;font-family:monospace;">${fmt(b.transport)}</td>
							<td style="padding:2px 0 2px 16px;color:#6c757d;">${__("Other Allowance")}</td>
							<td style="text-align:right;font-weight:600;font-family:monospace;">${fmt(b.other_allowance)}</td>
						</tr>
					</table>
				</div>
			`);
		},
	});
}

// ── Button injection ──────────────────────────────────────────────────────────

const _SKIP_TYPES = ["Section Break", "Column Break", "HTML", "Heading", "Button", "Tab Break"];
const _VALUE_TYPES = ["Currency", "Float", "Int", "Percent"];

function _inject_override_buttons(frm) {
	frm.meta.fields
		.filter(f => _VALUE_TYPES.includes(f.fieldtype) && !f.hidden && !_SKIP_TYPES.includes(f.fieldtype))
		.forEach(f => _inject_for_field(frm, f));
}

function _inject_for_field(frm, field_meta) {
	const fd = frm.fields_dict[field_meta.fieldname];
	if (!fd || !fd.$wrapper) return;

	// Avoid double-injection
	if (fd.$wrapper.find(".sco-btns").length) return;

	const label = field_meta.label || field_meta.fieldname;

	const $btns = $(`
		<span class="sco-btns" style="float:right;display:inline-flex;gap:3px;margin-top:1px;">
			<button class="btn btn-xs btn-default sco-hist"
				title="View salary history for ${label}"
				style="padding:2px 6px;line-height:1.2;">
				${_icon_clock()}
			</button>
			<button class="btn btn-xs btn-primary sco-edit"
				title="Edit ${label}"
				style="padding:2px 6px;line-height:1.2;">
				${_icon_pen()}
			</button>
		</span>
	`);

	fd.$wrapper.find(".control-label").first().append($btns);

	$btns.find(".sco-hist").on("click", e => {
		e.stopPropagation();
		_show_history_dialog(frm, field_meta);
	});
	$btns.find(".sco-edit").on("click", e => {
		e.stopPropagation();
		_show_edit_dialog(frm, field_meta);
	});
}

// ── History dialog ────────────────────────────────────────────────────────────

function _show_history_dialog(frm, field_meta) {
	const label = field_meta.label || field_meta.fieldname;

	frappe.call({
		method: "hr_suite.hr_suite.salary_override_api.get_available_years",
		args: { employee: frm.doc.employee, component_name: field_meta.fieldname },
		callback(r) {
			const years = r.message || [];
			const year_options = ["All Years", ...years];
			_render_history_dialog(frm, field_meta, label, year_options, "All Years");
		},
	});
}

function _render_history_dialog(frm, field_meta, label, year_options, selected_year) {
	const d = new frappe.ui.Dialog({
		title: `History — ${label}`,
		size: "large",
	});

	// Year filter
	const $filter_row = $(`
		<div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;">
			<span style="font-size:12px;color:#6c757d;font-weight:500;">Filter by Year:</span>
		</div>
	`);
	const $select = $("<select class='form-control form-control-sm' style='width:140px;'></select>");
	year_options.forEach(y => {
		$select.append(`<option value="${y}" ${y === selected_year ? "selected" : ""}>${y}</option>`);
	});
	$filter_row.append($select);

	const $table_wrap = $(`<div style="overflow-x:auto;"></div>`);
	const $table = $(`
		<table class="table table-bordered table-sm" style="font-size:12px;margin:0;">
			<thead style="background:#f8f9fa;">
				<tr>
					<th>Effective From</th>
					<th>Effective Until</th>
					<th style="text-align:right;">Last Value</th>
					<th style="text-align:right;">New Value</th>
					<th>Status</th>
					<th>Modified By</th>
					<th>Applied On</th>
				</tr>
			</thead>
			<tbody></tbody>
		</table>
	`);
	$table_wrap.append($table);

	d.$body.append($filter_row).append($table_wrap);

	function load_history(year) {
		frappe.call({
			method: "hr_suite.hr_suite.salary_override_api.get_component_history",
			args: {
				employee: frm.doc.employee,
				component_name: field_meta.fieldname,
				year: year === "All Years" ? null : year,
			},
			callback(r) {
				const rows = r.message || [];
				const $tbody = $table.find("tbody");
				$tbody.empty();

				if (!rows.length) {
					$tbody.append(`<tr><td colspan="7" style="text-align:center;color:#adb5bd;padding:20px;">No history found</td></tr>`);
					return;
				}

				rows.forEach(row => {
					const status_badge = _status_badge(row.status);
					$tbody.append(`
						<tr>
							<td>${frappe.format(row.start_date, {fieldtype:"Date"})}</td>
							<td>${row.end_date ? frappe.format(row.end_date, {fieldtype:"Date"}) : '<span style="color:#adb5bd">—</span>'}</td>
							<td style="text-align:right;font-family:monospace;">${frappe.format(row.last_value, {fieldtype:"Currency"})}</td>
							<td style="text-align:right;font-family:monospace;font-weight:600;">${frappe.format(row.new_value, {fieldtype:"Currency"})}</td>
							<td>${status_badge}</td>
							<td style="font-size:11px;">${row.modified_by_user || ""}</td>
							<td style="font-size:11px;">${row.applied_on ? frappe.format(row.applied_on, {fieldtype:"Datetime"}) : ""}</td>
						</tr>
					`);
				});
			},
		});
	}

	$select.on("change", function() {
		load_history($(this).val());
	});

	d.show();
	load_history(selected_year);
}

// ── Edit / Override dialog ────────────────────────────────────────────────────

function _show_edit_dialog(frm, field_meta) {
	const label = field_meta.label || field_meta.fieldname;
	const current_value = frm.doc[field_meta.fieldname] || 0;
	const today = frappe.datetime.get_today();

	const d = new frappe.ui.Dialog({
		title: `Edit Override: ${label}`,
		fields: [
			{
				fieldname: "component_display",
				fieldtype: "Data",
				label: "Component",
				default: label,
				read_only: 1,
			},
			{ fieldtype: "Column Break" },
			{
				fieldname: "start_date",
				fieldtype: "Date",
				label: "Effective From",
				reqd: 1,
				default: today,
				description: "Past/today → applied immediately. Future → scheduled.",
			},
			{ fieldtype: "Section Break" },
			{
				fieldname: "last_value",
				fieldtype: "Currency",
				label: "Last Value",
				default: current_value,
				read_only: 1,
			},
			{ fieldtype: "Column Break" },
			{
				fieldname: "new_value",
				fieldtype: "Currency",
				label: "Current Value",
				reqd: 1,
				description: "Enter the updated amount",
			},
			{ fieldtype: "Section Break" },
			{
				fieldname: "modified_info",
				fieldtype: "HTML",
				options: `
					<div style="font-size:11px;color:#6c757d;padding:4px 0;">
						<span><b>Modified On:</b> ${frappe.datetime.now_datetime()}</span>
						&nbsp;&nbsp;
						<span><b>Modified By:</b> ${frappe.session.user_fullname || frappe.session.user}</span>
					</div>
				`,
			},
			{
				fieldname: "notes",
				fieldtype: "Small Text",
				label: "Notes (optional)",
			},
		],
		primary_action_label: "Save & Submit",
		primary_action(values) {
			if (!values.new_value && values.new_value !== 0) {
				frappe.msgprint(__("Please enter a value."));
				return;
			}

			d.disable_primary_action();

			frappe.call({
				method: "hr_suite.hr_suite.salary_override_api.save_component_override",
				args: {
					employee: frm.doc.employee,
					component_name: field_meta.fieldname,
					component_label: label,
					new_value: values.new_value,
					effective_date: values.start_date,
					salary_structure_assignment: frm.doc.name,
					notes: values.notes || "",
				},
				callback(r) {
					if (r.exc) {
						d.enable_primary_action();
						return;
					}
					const result = r.message || {};
					const applied = result.status === "Applied";
					d.hide();

					if (applied) {
						// Refresh the form to show updated value
						frm.reload_doc();
						frappe.show_alert({
							message: `${label} updated to ${frappe.format(values.new_value, {fieldtype:"Currency"})}`,
							indicator: "green",
						});
					} else {
						frappe.show_alert({
							message: `Override scheduled for ${frappe.format(values.start_date, {fieldtype:"Date"})}`,
							indicator: "blue",
						});
					}
				},
				error() {
					d.enable_primary_action();
				},
			});
		},
	});

	d.show();
}

// ── Utilities ─────────────────────────────────────────────────────────────────

function _status_badge(status) {
	const map = {
		Applied:    "background:#d4edda;color:#155724;",
		Pending:    "background:#cce5ff;color:#004085;",
		Superseded: "background:#f8f9fa;color:#6c757d;",
	};
	const style = map[status] || "";
	return `<span style="padding:2px 8px;border-radius:12px;font-size:11px;${style}">${status}</span>`;
}

function _icon_clock() {
	return `<svg width="11" height="11" viewBox="0 0 24 24" fill="none"
		stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
		<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
	</svg>`;
}

function _icon_pen() {
	return `<svg width="11" height="11" viewBox="0 0 24 24" fill="none"
		stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
		<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
		<path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
	</svg>`;
}
