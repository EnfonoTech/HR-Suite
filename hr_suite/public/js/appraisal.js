// HR Suite — Appraisal form extensions (Steel Force Performance Appraisal Form 2025)
//
// Adds:
//   • "Load Criteria" / "Copy Appraiser Ratings to Reviewer" buttons
//   • the Attendance & Disciplinary History panel (custom_history_html)
//   • live total / grade recalculation as scores are typed into the grid
//
// The grade bands mirror hr_suite.hr_suite.performance.GRADE_BANDS — the server is
// authoritative on save; this is only so the user sees the number move.

const HR_SUITE_RATINGS_FIELD = "custom_criterion_ratings";
const HR_SUITE_MAX_PER_CRITERION = 5;
const HR_SUITE_REFERENCE_MAX_TOTAL = 75;
const HR_SUITE_GRADE_BANDS = [
	["Excellent", 60],
	["Very Good", 53],
	["Good", 45],
	["Average", 31],
];

frappe.ui.form.on("Appraisal", {
	refresh: function (frm) {
		if (!frm.fields_dict[HR_SUITE_RATINGS_FIELD]) return;

		if (!frm.is_new() && frm.doc.docstatus === 0) {
			frm.add_custom_button(
				__("Load Criteria"),
				function () {
					hr_suite_load_criteria(frm);
				},
				__("Steel Force Appraisal")
			);

			frm.add_custom_button(
				__("Copy Appraiser Ratings to Reviewer"),
				function () {
					hr_suite_copy_ratings(frm);
				},
				__("Steel Force Appraisal")
			);
		}

		hr_suite_recalculate_totals(frm);
		hr_suite_render_history(frm);
	},

	employee: function (frm) {
		hr_suite_render_history(frm);
	},

	custom_period_from: function (frm) {
		hr_suite_render_history(frm);
	},

	custom_period_to: function (frm) {
		hr_suite_render_history(frm);
	},
});

// Grid row removal is triggered with the CHILD doctype as the handler key —
// grid_row.js:110-114 calls script_manager.trigger(fieldname + "_remove", this.doc.doctype, ...)
// and script_manager.get_handlers() looks the event up under that doctype. Registering
// "<fieldname>_remove" on the parent "Appraisal" handler never fires.
frappe.ui.form.on("Appraisal Criterion Rating", {
	custom_criterion_ratings_remove: function (frm) {
		hr_suite_recalculate_totals(frm);
	},

	appraiser_rating: function (frm, cdt, cdn) {
		hr_suite_set_variance(frm, cdt, cdn);
		hr_suite_recalculate_totals(frm);
	},

	reviewer_rating: function (frm, cdt, cdn) {
		hr_suite_set_variance(frm, cdt, cdn);
		hr_suite_recalculate_totals(frm);
	},
});

// ── Actions ───────────────────────────────────────────────────────────────────

function hr_suite_load_criteria(frm) {
	frappe.call({
		method: "hr_suite.hr_suite.performance.load_criteria",
		args: { appraisal: frm.doc.name },
		freeze: true,
		freeze_message: __("Loading criteria..."),
		callback: function (r) {
			if (!r.message) return;
			frm.reload_doc();
			if (r.message.added) {
				frappe.show_alert({
					message: __("{0} criteria added", [r.message.added]),
					indicator: "green",
				});
			} else {
				frappe.show_alert({
					message: __("All criteria are already loaded"),
					indicator: "blue",
				});
			}
		},
	});
}

function hr_suite_copy_ratings(frm) {
	frappe.confirm(
		__(
			"Copy every Appraiser score onto the Reviewer column? Existing Reviewer comments on the rows that change will be cleared."
		),
		function () {
			frappe.call({
				method: "hr_suite.hr_suite.performance.copy_appraiser_ratings_to_reviewer",
				args: { appraisal: frm.doc.name },
				freeze: true,
				freeze_message: __("Copying ratings..."),
				callback: function (r) {
					if (!r.message) return;
					frm.reload_doc();
					frappe.show_alert({
						message: __("{0} rows updated", [r.message.copied]),
						indicator: "green",
					});
				},
			});
		}
	);
}

// ── Live totals ───────────────────────────────────────────────────────────────

function hr_suite_set_variance(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row) return;
	const appraiser = cint(row.appraiser_rating);
	const reviewer = cint(row.reviewer_rating);
	frappe.model.set_value(cdt, cdn, "variance", appraiser && reviewer ? reviewer - appraiser : 0);
}

function hr_suite_grade(score, maxTotal) {
	score = cint(score);
	maxTotal = cint(maxTotal);
	if (!maxTotal || score <= 0) return "";
	for (const [grade, band] of HR_SUITE_GRADE_BANDS) {
		// Integer arithmetic so a rescaled maximum never opens a band hole.
		if (score * HR_SUITE_REFERENCE_MAX_TOTAL >= band * maxTotal) return grade;
	}
	return "Poor";
}

// Display-only refresh: values are written straight onto frm.doc and the field is
// redrawn, so simply opening a saved Appraisal never marks the form dirty. The
// server recomputes all five fields in validate_appraisal() on every save.
function hr_suite_set_display(frm, fieldname, value) {
	if (frm.doc[fieldname] === value) return;
	frm.doc[fieldname] = value;
	frm.refresh_field(fieldname);
}

function hr_suite_recalculate_totals(frm) {
	if (frm.doc.docstatus !== 0) return;

	const rows = frm.doc[HR_SUITE_RATINGS_FIELD] || [];
	let appraiserTotal = 0;
	let reviewerTotal = 0;
	let appraiserScoredRows = 0;
	let reviewerScoredRows = 0;

	rows.forEach(function (row) {
		appraiserTotal += cint(row.appraiser_rating);
		reviewerTotal += cint(row.reviewer_rating);
		if (cint(row.appraiser_rating)) appraiserScoredRows++;
		if (cint(row.reviewer_rating)) reviewerScoredRows++;
	});

	const maxTotal = rows.length * HR_SUITE_MAX_PER_CRITERION;
	// Mirrors validate_appraisal(): the official grade follows the Reviewer only once
	// the Reviewer column is complete, otherwise a half-filled column understates it.
	const reviewerComplete = reviewerScoredRows > 0 && reviewerScoredRows >= appraiserScoredRows;

	hr_suite_set_display(frm, "custom_appraiser_total", appraiserTotal);
	hr_suite_set_display(frm, "custom_reviewer_total", reviewerTotal);
	hr_suite_set_display(frm, "custom_max_total", maxTotal);
	hr_suite_set_display(frm, "custom_appraiser_grade", hr_suite_grade(appraiserTotal, maxTotal));
	hr_suite_set_display(
		frm,
		"custom_performance_grade",
		hr_suite_grade(reviewerComplete ? reviewerTotal : appraiserTotal, maxTotal)
	);
}

// ── Attendance & disciplinary history ─────────────────────────────────────────

function hr_suite_render_history(frm) {
	const wrapper = frm.fields_dict.custom_history_html
		? frm.fields_dict.custom_history_html.$wrapper
		: null;
	if (!wrapper) return;

	const employee = frm.doc.employee;
	const fromDate = frm.doc.custom_period_from;
	const toDate = frm.doc.custom_period_to;

	if (!employee || !fromDate || !toDate) {
		wrapper.html(
			`<div class="text-muted">${__(
				"Set the Employee and the Evaluation Period to see the attendance and disciplinary history."
			)}</div>`
		);
		return;
	}

	wrapper.html(`<div class="text-muted">${__("Loading history...")}</div>`);

	frappe.call({
		method: "hr_suite.hr_suite.performance.get_performance_history",
		args: { employee: employee, from_date: fromDate, to_date: toDate },
		callback: function (r) {
			if (!r.message) {
				wrapper.html(`<div class="text-muted">${__("No history available.")}</div>`);
				return;
			}
			wrapper.html(hr_suite_history_html(r.message));
		},
		error: function () {
			wrapper.html(
				`<div class="text-muted">${__("History could not be loaded.")}</div>`
			);
		},
	});
}

function hr_suite_history_html(data) {
	const a = data.attendance || {};
	const rows = [
		[__("Present"), a.present || 0],
		[__("Absent"), a.absent || 0],
		[__("Half Day"), a.half_day || 0],
		[__("On Leave"), a.on_leave || 0],
		[__("Work From Home"), a.work_from_home || 0],
		[__("Late Entry"), a.late_entry || 0],
		[__("Early Exit"), a.early_exit || 0],
		[__("Leave Without Pay (days)"), data.leave_without_pay_days || 0],
	];

	let html = `<div class="hr-suite-appraisal-history">`;
	html += `<h6>${__("Attendance")} <span class="text-muted">(${frappe.utils.escape_html(
		data.from_date
	)} → ${frappe.utils.escape_html(data.to_date)})</span></h6>`;
	html += `<table class="table table-bordered table-sm"><tbody>`;
	rows.forEach(function (row) {
		html += `<tr><td style="width:60%">${row[0]}</td><td><b>${row[1]}</b></td></tr>`;
	});
	html += `</tbody></table>`;

	const discipline = data.disciplinary || [];
	html += `<h6>${__("Disciplinary History")}</h6>`;
	if (!discipline.length) {
		html += `<div class="text-muted">${__("No disciplinary records in this period.")}</div>`;
	} else {
		html += `<table class="table table-bordered table-sm"><thead><tr>
			<th>${__("Date")}</th><th>${__("Type")}</th><th>${__("Reference")}</th><th>${__(
			"Details"
		)}</th></tr></thead><tbody>`;
		discipline.forEach(function (item) {
			const details = Object.keys(item.details || {})
				.map(function (key) {
					return `${frappe.utils.escape_html(key)}: ${frappe.utils.escape_html(
						String(item.details[key])
					)}`;
				})
				.join(", ");
			const route = `/app/${frappe.router.slug(item.doctype)}/${encodeURIComponent(item.name)}`;
			html += `<tr>
				<td>${frappe.utils.escape_html(item.date)}</td>
				<td>${__(item.doctype)}</td>
				<td><a href="${route}">${frappe.utils.escape_html(item.name)}</a></td>
				<td>${details}</td>
			</tr>`;
		});
		html += `</tbody></table>`;
	}

	html += `<div class="text-muted small">${__(
		"Punctuality, Attendance and Discipline must be scored strictly from this historical data."
	)}</div>`;
	html += `</div>`;
	return html;
}
