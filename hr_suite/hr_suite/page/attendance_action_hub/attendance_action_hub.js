frappe.provide("hr_suite");

frappe.pages["attendance-action-hub"].on_page_load = function (wrapper) {
	new hr_suite.AttendanceActionHub(wrapper);
};

hr_suite.AttendanceActionHub = class AttendanceActionHub {
	constructor(wrapper) {
		this.wrapper = wrapper;
		this.rows = [];
		this.canCreateAbsenceCase = frappe.model.can_create("Absence Case");
		this.ensureStyles();
		this.page = frappe.ui.make_app_page({
			parent: wrapper,
			title: __("Attendance Action Hub"),
			single_column: true,
		});
		this.makeFilters();
		this.makeLayout();
		this.bindEvents();
		this.page.set_primary_action(__("Refresh"), () => this.refresh());
		this.page.add_menu_item(
			__("Open Team Attendance Review"),
			() => this.openReport(),
		);
		this.refresh();
	}

	ensureStyles() {
		if (document.getElementById("attendance-action-hub-style")) {
			return;
		}

		const style = document.createElement("style");
		style.id = "attendance-action-hub-style";
		style.textContent = `
			.attendance-action-hub {
				display: grid;
				gap: 16px;
				padding: 8px 0 24px;
			}

			.attendance-action-hub__hero {
				display: grid;
				grid-template-columns: minmax(0, 1.7fr) minmax(260px, 1fr);
				gap: 16px;
				align-items: stretch;
			}

			.attendance-action-hub__panel,
			.attendance-action-hub__card {
				background: linear-gradient(180deg, #ffffff 0%, #f6fbf8 100%);
				border: 1px solid #d6e6dc;
				border-radius: 18px;
				box-shadow: 0 12px 30px rgba(21, 67, 45, 0.08);
			}

			.attendance-action-hub__panel {
				padding: 20px 22px;
			}

			.attendance-action-hub__eyebrow {
				font-size: 12px;
				font-weight: 700;
				letter-spacing: 0.08em;
				text-transform: uppercase;
				color: #2a6b49;
				margin-bottom: 8px;
			}

			.attendance-action-hub__title {
				font-size: 26px;
				line-height: 1.2;
				font-weight: 700;
				color: #173826;
				margin: 0 0 8px;
			}

			.attendance-action-hub__subtitle {
				font-size: 14px;
				line-height: 1.7;
				color: #4d6658;
				margin: 0;
			}

			.attendance-action-hub__scope {
				display: flex;
				flex-wrap: wrap;
				gap: 8px;
				margin-top: 14px;
			}

			.attendance-action-hub__scope-chip,
			.attendance-action-hub__flag,
			.attendance-action-hub__state {
				display: inline-flex;
				align-items: center;
				gap: 6px;
				padding: 6px 10px;
				border-radius: 999px;
				font-size: 12px;
				font-weight: 600;
			}

			.attendance-action-hub__scope-chip {
				background: #edf6f0;
				color: #2d5a43;
			}

			.attendance-action-hub__hero-metrics {
				display: grid;
				grid-template-columns: repeat(2, minmax(0, 1fr));
				gap: 12px;
			}

			.attendance-action-hub__metric {
				padding: 16px;
				border-radius: 16px;
				background: #f0f7f3;
				border: 1px solid #d4e6db;
			}

			.attendance-action-hub__metric--alert {
				background: #fff3ea;
				border-color: #f0c5a5;
			}

			.attendance-action-hub__metric-label {
				font-size: 12px;
				font-weight: 600;
				color: #4d6658;
				margin-bottom: 6px;
			}

			.attendance-action-hub__metric-value {
				font-size: 28px;
				font-weight: 700;
				color: #173826;
			}

			.attendance-action-hub__summary {
				display: grid;
				grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
				gap: 12px;
			}

			.attendance-action-hub__summary-card {
				padding: 16px;
			}

			.attendance-action-hub__summary-card--alert {
				background: linear-gradient(180deg, #fffaf4 0%, #fff1e1 100%);
				border-color: #f0ca9e;
			}

			.attendance-action-hub__summary-card--ok {
				background: linear-gradient(180deg, #ffffff 0%, #f4fbf7 100%);
			}

			.attendance-action-hub__summary-value {
				font-size: 30px;
				font-weight: 700;
				color: #173826;
				margin-bottom: 6px;
			}

			.attendance-action-hub__summary-label {
				font-size: 13px;
				font-weight: 600;
				color: #4d6658;
			}

			.attendance-action-hub__results-header {
				display: flex;
				justify-content: space-between;
				align-items: end;
				gap: 12px;
				margin-bottom: 6px;
			}

			.attendance-action-hub__results-title {
				font-size: 20px;
				font-weight: 700;
				color: #173826;
				margin: 0;
			}

			.attendance-action-hub__results-subtitle {
				font-size: 13px;
				color: #4d6658;
				margin: 4px 0 0;
			}

			.attendance-action-hub__cards {
				display: grid;
				grid-template-columns: repeat(auto-fit, minmax(330px, 1fr));
				gap: 14px;
			}

			.attendance-action-hub__card {
				padding: 18px;
			}

			.attendance-action-hub__card-head {
				display: flex;
				justify-content: space-between;
				gap: 12px;
				align-items: start;
				margin-bottom: 12px;
			}

			.attendance-action-hub__card-title {
				font-size: 18px;
				font-weight: 700;
				color: #173826;
				margin: 0 0 4px;
			}

			.attendance-action-hub__card-meta {
				font-size: 12px;
				color: #597162;
			}

			.attendance-action-hub__state {
				background: #edf6f0;
				color: #244c37;
			}

			.attendance-action-hub__state--alert {
				background: #fff0e3;
				color: #8a4a17;
			}

			.attendance-action-hub__flags {
				display: flex;
				flex-wrap: wrap;
				gap: 8px;
				margin-bottom: 12px;
			}

			.attendance-action-hub__flag {
				background: #edf6f0;
				color: #244c37;
			}

			.attendance-action-hub__flag--alert {
				background: #fff2e8;
				color: #8a4a17;
			}

			.attendance-action-hub__details {
				display: grid;
				grid-template-columns: repeat(2, minmax(0, 1fr));
				gap: 10px;
				margin-bottom: 14px;
			}

			.attendance-action-hub__detail {
				padding: 10px 12px;
				border-radius: 12px;
				background: #f7fbf8;
				border: 1px solid #e1eee6;
			}

			.attendance-action-hub__detail-label {
				font-size: 11px;
				font-weight: 700;
				color: #668172;
				text-transform: uppercase;
				letter-spacing: 0.04em;
				margin-bottom: 4px;
			}

			.attendance-action-hub__detail-value {
				font-size: 14px;
				font-weight: 600;
				color: #1d3b2a;
			}

			.attendance-action-hub__actions {
				display: flex;
				flex-wrap: wrap;
				gap: 8px;
			}

			.attendance-action-hub__empty {
				padding: 24px;
				text-align: center;
			}

			.attendance-action-hub__loading {
				min-height: 120px;
				display: grid;
				place-items: center;
				color: #4d6658;
			}

			@media (max-width: 992px) {
				.attendance-action-hub__hero {
					grid-template-columns: 1fr;
				}

				.attendance-action-hub__details {
					grid-template-columns: 1fr;
				}
			}
		`;
		document.head.appendChild(style);
	}

	makeFilters() {
		this.filters = {
			attendance_date: this.page.add_field({
				label: __("Attendance Date"),
				fieldname: "attendance_date",
				fieldtype: "Date",
				default: frappe.datetime.get_today(),
				change: () => this.refresh(),
			}),
			company: this.page.add_field({
				label: __("Company"),
				fieldname: "company",
				fieldtype: "Link",
				options: "Company",
				change: () => this.refresh(),
			}),
			branch: this.page.add_field({
				label: __("Branch"),
				fieldname: "branch",
				fieldtype: "Link",
				options: "Branch",
				change: () => this.refresh(),
			}),
			department: this.page.add_field({
				label: __("Department"),
				fieldname: "department",
				fieldtype: "Link",
				options: "Department",
				change: () => this.refresh(),
			}),
			employee: this.page.add_field({
				label: __("Employee"),
				fieldname: "employee",
				fieldtype: "Link",
				options: "Employee",
				change: () => this.refresh(),
			}),
			only_exceptions: this.page.add_field({
				label: __("Only Exceptions"),
				fieldname: "only_exceptions",
				fieldtype: "Check",
				default: 1,
				change: () => this.refresh(),
			}),
		};
	}

	makeLayout() {
		this.$container = $("<div class='attendance-action-hub'></div>").appendTo(this.page.main);
		this.$hero = $("<div></div>").appendTo(this.$container);
		this.$summary = $("<div class='attendance-action-hub__summary'></div>").appendTo(this.$container);
		this.$results = $("<div></div>").appendTo(this.$container);
	}

	bindEvents() {
		this.$container.on("click", "[data-action]", (event) => {
			const $button = $(event.currentTarget);
			const rowIndex = Number.parseInt($button.attr("data-row-index"), 10);
			const row = this.rows[rowIndex];

			if (!row) {
				return;
			}

			this.handleAction($button.attr("data-action"), row);
		});
	}

	getFilters() {
		const filters = {};
		Object.entries(this.filters).forEach(([key, field]) => {
			const value = field.get_value();
			if (value !== undefined && value !== null && value !== "") {
				filters[key] = value;
			}
		});
		return filters;
	}

	refresh() {
		const filters = this.getFilters();
		this.renderLoading(filters);

		if (this.lastRequest && this.lastRequest.abort) {
			this.lastRequest.abort();
		}

		this.lastRequest = frappe.call({
			method: "frappe.desk.query_report.run",
			type: "GET",
			args: {
				report_name: "Team Attendance Review",
				filters,
			},
			callback: (response) => {
				const payload = response.message || {};
				this.rows = payload.result || [];
				this.render(filters);
			},
			error: () => {
				this.rows = [];
				this.renderError(filters);
			},
			always: () => {
				this.lastRequest = null;
			},
		});
	}

	renderLoading(filters) {
		this.$hero.html(this.renderHero(filters, this.getEmptyMetrics(), true));
		this.$summary.html(
			new Array(6)
				.fill("")
				.map(
					() =>
						`<div class='attendance-action-hub__card attendance-action-hub__summary-card'><div class='attendance-action-hub__loading'>${__("Loading attendance cases...")}</div></div>`,
				)
				.join(""),
		);
		this.$results.html(
			`<div class='attendance-action-hub__panel attendance-action-hub__loading'>${__("Loading attendance actions...")}</div>`,
		);
	}

	render(filters) {
		const metrics = this.getMetrics(this.rows);
		this.$hero.html(this.renderHero(filters, metrics, false));
		this.$summary.html(this.renderSummary(metrics));
		this.$results.html(this.renderResults(filters));
	}

	renderError(filters) {
		this.$hero.html(this.renderHero(filters, this.getEmptyMetrics(), false));
		this.$summary.empty();
		this.$results.html(
			`<div class="attendance-action-hub__panel attendance-action-hub__empty">
				<h3 class="attendance-action-hub__results-title">${this.escapeHtml(
					__("Unable to load attendance actions"),
				)}</h3>
				<p class="attendance-action-hub__results-subtitle">${this.escapeHtml(
					__("Use the report menu above or refresh the page after checking permissions and filters."),
				)}</p>
			</div>`,
		);
	}

	getEmptyMetrics() {
		return {
			total: 0,
			flagged: 0,
			noMovement: 0,
			openShift: 0,
			timeExceptions: 0,
			voiceFollowUp: 0,
		};
	}

	getMetrics(rows) {
		return {
			total: rows.length,
			flagged: rows.filter((row) => this.hasFlags(row)).length,
			noMovement: rows.filter((row) => row._flag_no_movement).length,
			openShift: rows.filter((row) => row._flag_open_shift).length,
			timeExceptions: rows.filter((row) => row._flag_late || row._flag_early_exit).length,
			voiceFollowUp: rows.filter(
				(row) => row._flag_voice_profile_missing || row._flag_voice_verification_pending,
			).length,
		};
	}

	renderHero(filters, metrics, isLoading) {
		const scopeChips = this.getScopeChips(filters)
			.map(
				(chip) =>
					`<span class="attendance-action-hub__scope-chip">${this.escapeHtml(chip)}</span>`,
			)
			.join("");
		const heroMetrics = [
			{
				label: __("In Scope"),
				value: metrics.total,
				alert: false,
			},
			{
				label: __("Needs Action"),
				value: metrics.flagged,
				alert: metrics.flagged > 0,
			},
			{
				label: __("Voice Follow-up"),
				value: metrics.voiceFollowUp,
				alert: metrics.voiceFollowUp > 0,
			},
			{
				label: __("Time Exceptions"),
				value: metrics.timeExceptions,
				alert: metrics.timeExceptions > 0,
			},
		]
			.map(
				(metric) => `
					<div class="attendance-action-hub__metric ${metric.alert ? "attendance-action-hub__metric--alert" : ""}">
						<div class="attendance-action-hub__metric-label">${this.escapeHtml(metric.label)}</div>
						<div class="attendance-action-hub__metric-value">${this.escapeHtml(String(metric.value))}</div>
					</div>`,
			)
			.join("");

		return `
			<div class="attendance-action-hub__hero">
				<section class="attendance-action-hub__panel">
					<div class="attendance-action-hub__eyebrow">${this.escapeHtml(
						__("Supervisor Controls"),
					)}</div>
					<h2 class="attendance-action-hub__title">${this.escapeHtml(
						__("Attendance Action Hub"),
					)}</h2>
					<p class="attendance-action-hub__subtitle">${this.escapeHtml(
						isLoading
							? __("Refreshing attendance exceptions and follow-up actions from the daily review report.")
							: __(
								"Review today's attendance gaps, voice verification issues, and open shifts without leaving the supervisor workspace.",
							),
					)}</p>
					<div class="attendance-action-hub__scope">${scopeChips}</div>
				</section>
				<section class="attendance-action-hub__panel">
					<div class="attendance-action-hub__hero-metrics">${heroMetrics}</div>
				</section>
			</div>`;
	}

	getScopeChips(filters) {
		const chips = [
			`${__("Date")}: ${filters.attendance_date || frappe.datetime.get_today()}`,
		];

		[
			["company", __("Company")],
			["branch", __("Branch")],
			["department", __("Department")],
			["employee", __("Employee")],
		].forEach(([key, label]) => {
			if (filters[key]) {
				chips.push(`${label}: ${filters[key]}`);
			}
		});

		chips.push(
			filters.only_exceptions
				? __("Only exceptions")
				: __("All rows"),
		);

		return chips;
	}

	renderSummary(metrics) {
		const cards = [
			{
				label: __("Exceptions"),
				value: metrics.flagged,
				state: metrics.flagged > 0 ? "alert" : "ok",
			},
			{
				label: __("No Movement"),
				value: metrics.noMovement,
				state: metrics.noMovement > 0 ? "alert" : "ok",
			},
			{
				label: __("Open Shifts"),
				value: metrics.openShift,
				state: metrics.openShift > 0 ? "alert" : "ok",
			},
			{
				label: __("Time Exceptions"),
				value: metrics.timeExceptions,
				state: metrics.timeExceptions > 0 ? "alert" : "ok",
			},
			{
				label: __("Voice Follow-up"),
				value: metrics.voiceFollowUp,
				state: metrics.voiceFollowUp > 0 ? "alert" : "ok",
			},
			{
				label: __("Employees in Scope"),
				value: metrics.total,
				state: "ok",
			},
		];

		return cards
			.map(
				(card) => `
					<section class="attendance-action-hub__card attendance-action-hub__summary-card attendance-action-hub__summary-card--${card.state}">
						<div class="attendance-action-hub__summary-value">${this.escapeHtml(String(card.value))}</div>
						<div class="attendance-action-hub__summary-label">${this.escapeHtml(card.label)}</div>
					</section>`,
			)
			.join("");
	}

	renderResults(filters) {
		if (!this.rows.length) {
			return `
				<div class="attendance-action-hub__panel attendance-action-hub__empty">
					<h3 class="attendance-action-hub__results-title">${this.escapeHtml(
						__("No attendance rows found"),
					)}</h3>
					<p class="attendance-action-hub__results-subtitle">${this.escapeHtml(
						__(
							"Adjust the selected filters or clear the exceptions-only switch to inspect the full team schedule.",
						),
					)}</p>
				</div>`;
		}

		const cards = this.rows.map((row, rowIndex) => this.renderCard(row, rowIndex)).join("");

		return `
			<div class="attendance-action-hub__results-header">
				<div>
					<h3 class="attendance-action-hub__results-title">${this.escapeHtml(
						__("Follow-up Queue"),
					)}</h3>
					<p class="attendance-action-hub__results-subtitle">${this.escapeHtml(
						__(
							"Use the direct actions on each card to open the employee, attendance evidence, or the related absence workflow.",
						),
					)}</p>
				</div>
				<div class="attendance-action-hub__state ${
					this.getMetrics(this.rows).flagged > 0 ? "attendance-action-hub__state--alert" : ""
				}">${this.escapeHtml(
					`${__("Rows")}: ${this.rows.length}`,
				)}</div>
			</div>
			<div class="attendance-action-hub__cards">${cards}</div>`;
	}

	renderCard(row, rowIndex) {
		const flagLabels = this.getFlagLabels(row);
		const actions = [
			this.renderActionButton(rowIndex, "open-employee", __("Open Employee"), "btn-default"),
			this.renderActionButton(rowIndex, "open-report", __("Review in Report"), "btn-default"),
		];

		if (row._daily_attendance_name) {
			actions.push(
				this.renderActionButton(
					rowIndex,
					"open-attendance",
						__("Open Daily Attendance"),
					"btn-default",
				),
			);
		}

		if (row._latest_checkin_name) {
			actions.push(
				this.renderActionButton(
					rowIndex,
					"open-checkin",
						__("Open Last Checkin"),
					"btn-default",
				),
			);
		}

		if (row._voice_profile_name) {
			actions.push(
				this.renderActionButton(
					rowIndex,
					"open-voice-profile",
						__("Open Voice Profile"),
					"btn-default",
				),
			);
		}

		if (this.canCreateAbsenceCase && this.canCreateAbsenceCaseForRow(row)) {
			actions.push(
				this.renderActionButton(
					rowIndex,
					"create-absence-case",
					__("Create Absence Case"),
					"btn-primary",
				),
			);
		}

		return `
			<section class="attendance-action-hub__card">
				<div class="attendance-action-hub__card-head">
					<div>
						<h4 class="attendance-action-hub__card-title">${this.escapeHtml(
							row.employee_name || row.employee,
						)}</h4>
						<div class="attendance-action-hub__card-meta">${this.escapeHtml(
							[row.employee, row.department, row.branch].filter(Boolean).join(" • "),
						)}</div>
					</div>
					<div class="attendance-action-hub__state ${
						this.hasFlags(row) ? "attendance-action-hub__state--alert" : ""
					}">${this.escapeHtml(
						this.hasFlags(row)
							? __("Needs Action")
							: __("On Track"),
					)}</div>
				</div>
				<div class="attendance-action-hub__flags">${flagLabels
					.map(
						(label) =>
							`<span class="attendance-action-hub__flag ${
								this.hasFlags(row) ? "attendance-action-hub__flag--alert" : ""
							}">${this.escapeHtml(label)}</span>`,
					)
					.join("")}</div>
				<div class="attendance-action-hub__details">
					${this.renderDetail(__("Attendance"), row.attendance_status)}
					${this.renderDetail(__("Shift"), row.shift_type || __("Not set"))}
					${this.renderDetail(__("Shift Status"), row.schedule_status)}
					${this.renderDetail(__("Location"), row.attendance_location)}
					${this.renderDetail(__("Expected Start"), this.formatDateTime(row.expected_start))}
					${this.renderDetail(__("Expected End"), this.formatDateTime(row.expected_end))}
					${this.renderDetail(__("First In"), this.formatDateTime(row.first_in))}
					${this.renderDetail(__("Last Out"), this.formatDateTime(row.last_out))}
					${this.renderDetail(__("Late Minutes"), String(row.late_minutes || 0))}
					${this.renderDetail(__("Early Exit"), String(row.early_exit_minutes || 0))}
					${this.renderDetail(__("Voice Policy"), row.voice_policy || __("Disabled"))}
					${this.renderDetail(__("Voice Status"), row.voice_verification_status)}
				</div>
				<div class="attendance-action-hub__actions">${actions.join("")}</div>
			</section>`;
	}

	renderActionButton(rowIndex, action, label, buttonClass) {
		return `<button class="btn btn-sm ${buttonClass}" data-action="${action}" data-row-index="${rowIndex}">${this.escapeHtml(
			label,
		)}</button>`;
	}

	renderDetail(label, value) {
		return `
			<div class="attendance-action-hub__detail">
				<div class="attendance-action-hub__detail-label">${this.escapeHtml(label)}</div>
				<div class="attendance-action-hub__detail-value">${this.escapeHtml(
					value || __("Not recorded"),
				)}</div>
			</div>`;
	}

	getFlagLabels(row) {
		const flags = [];
		if (row._flag_no_movement) {
			flags.push(__("No Movement"));
		}
		if (row._flag_open_shift) {
			flags.push(__("Open Shift"));
		}
		if (row._flag_late) {
			flags.push(__("Late"));
		}
		if (row._flag_early_exit) {
			flags.push(__("Early Exit"));
		}
		if (row._flag_voice_profile_missing) {
			flags.push(__("Voice Profile Missing"));
		}
		if (row._flag_voice_verification_pending) {
			flags.push(__("Voice Verification Pending"));
		}

		if (!flags.length) {
			flags.push(__("On Track"));
		}

		return flags;
	}

	hasFlags(row) {
		return Boolean(
			row._flag_no_movement ||
				row._flag_open_shift ||
				row._flag_late ||
				row._flag_early_exit ||
				row._flag_voice_profile_missing ||
				row._flag_voice_verification_pending,
		);
	}

	canCreateAbsenceCaseForRow(row) {
		return Boolean(row._flag_no_movement || row._flag_open_shift || row._flag_late || row._flag_early_exit);
	}

	handleAction(action, row) {
		switch (action) {
			case "open-employee":
				frappe.set_route("Form", "Employee", row.employee);
				break;
			case "open-report":
				this.openReport(row);
				break;
			case "open-attendance":
				if (row._daily_attendance_name) {
					frappe.set_route("Form", "Saudi Daily Attendance", row._daily_attendance_name);
				}
				break;
			case "open-checkin":
				if (row._latest_checkin_name) {
					frappe.set_route("Form", "Saudi Employee Checkin", row._latest_checkin_name);
				}
				break;
			case "open-voice-profile":
				if (row._voice_profile_name) {
					frappe.set_route("Form", "Saudi Employee Voice Profile", row._voice_profile_name);
				}
				break;
			case "create-absence-case":
				frappe.new_doc("Absence Case", this.getAbsenceCaseDefaults(row));
				break;
		}
	}

	openReport(row) {
		const filters = this.getFilters();
		const routeFilters = {
			attendance_date: filters.attendance_date || frappe.datetime.get_today(),
			only_exceptions: 0,
			company: row ? row.company || filters.company : filters.company,
			branch: row ? row.branch || filters.branch : filters.branch,
			department: row ? row.department || filters.department : filters.department,
			employee: row ? row.employee : filters.employee,
		};

		Object.keys(routeFilters).forEach((key) => {
			if (routeFilters[key] === undefined || routeFilters[key] === null || routeFilters[key] === "") {
				delete routeFilters[key];
			}
		});

		frappe.route_options = routeFilters;
		frappe.set_route("query-report", "Team Attendance Review");
	}

	getAbsenceCaseDefaults(row) {
		const attendanceDate = this.filters.attendance_date.get_value() || frappe.datetime.get_today();
		return {
			employee: row.employee,
			company: row.company,
			department: row.department,
			absence_type: this.getAbsenceType(row),
			absence_start_date: attendanceDate,
			absence_end_date: attendanceDate,
			description: this.getAbsenceDescription(row, attendanceDate),
		};
	}

	getAbsenceType(row) {
		if (row._flag_no_movement) {
			return "No Call No Show";
		}
		if (row._flag_open_shift || row._flag_early_exit) {
			return "Partial Absence";
		}
		if (row._flag_late) {
			return "Repeated Late Attendance";
		}
		return "Other";
	}

	getAbsenceDescription(row, attendanceDate) {
		const lines = [
			`${__("Attendance follow-up date")} : ${attendanceDate}`,
			`${__("Employee")} : ${row.employee} - ${row.employee_name || ""}`,
			`${__("Flags")} : ${this.getFlagLabels(row).join(", ")}`,
			`${__("Attendance status")} : ${row.attendance_status || ""}`,
			`${__("Shift status")} : ${row.schedule_status || ""}`,
			`${__("Expected start")} : ${this.formatDateTime(row.expected_start)}`,
			`${__("Expected end")} : ${this.formatDateTime(row.expected_end)}`,
			`${__("First in")} : ${this.formatDateTime(row.first_in)}`,
			`${__("Last out")} : ${this.formatDateTime(row.last_out)}`,
			`${__("Late minutes")} : ${row.late_minutes || 0}`,
			`${__("Early exit minutes")} : ${row.early_exit_minutes || 0}`,
		];
		return lines.join("\n");
	}

	formatDateTime(value) {
		if (!value) {
			return __("Not recorded");
		}

		return frappe.datetime.str_to_user(value);
	}

	escapeHtml(value) {
		return frappe.utils.escape_html(value == null ? "" : String(value));
	}
};