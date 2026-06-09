frappe.provide("hr_suite");

frappe.pages["professional-hr-entry"].on_page_load = function (wrapper) {
	wrapper.professional_hr_entry = new hr_suite.ProfessionalHrEntry(wrapper);
};

frappe.pages["professional-hr-entry"].on_page_show = function (wrapper) {
	wrapper.professional_hr_entry?.loadEntry();
};

hr_suite.ProfessionalHrEntry = class ProfessionalHrEntry {
	constructor(wrapper) {
		this.wrapper = wrapper;
		this.feature = null;
		this.controls = [];
		this.page = frappe.ui.make_app_page({
			parent: wrapper,
			title: __("Professional HR Entry"),
			single_column: true,
		});
		this.ensureStyles();
		this.renderLoading();
		this.loadEntry();
		this.page.set_primary_action(__("Professional HR Hub"), () => this.open("/app/professional-hr-hub"));
	}

	ensureStyles() {
		if (document.getElementById("professional-hr-entry-style")) {
			return;
		}
		const style = document.createElement("style");
		style.id = "professional-hr-entry-style";
		style.textContent = `
			.professional-hr-entry {
				display: grid;
				gap: 18px;
				padding: 8px 0 30px;
				color: #172b4d;
			}
			.professional-hr-entry__panel {
				background: #ffffff;
				border: 1px solid #dfe3eb;
				border-radius: 8px;
				box-shadow: 0 8px 24px rgba(23, 43, 77, 0.06);
				padding: 22px;
			}
			.professional-hr-entry__hero {
				display: grid;
				grid-template-columns: minmax(0, 1.25fr) minmax(280px, 0.75fr);
				gap: 14px;
			}
			.professional-hr-entry__eyebrow {
				font-size: 12px;
				font-weight: 700;
				text-transform: uppercase;
				color: #216e4e;
				margin-bottom: 8px;
			}
			.professional-hr-entry__title {
				font-size: 26px;
				font-weight: 700;
				line-height: 1.25;
				margin: 0 0 8px;
			}
			.professional-hr-entry__text,
			.professional-hr-entry__muted {
				font-size: 13px;
				line-height: 1.65;
				color: #5e6c84;
				margin: 0;
			}
			.professional-hr-entry__metrics {
				display: grid;
				gap: 10px;
			}
			.professional-hr-entry__metric {
				display: flex;
				justify-content: space-between;
				gap: 12px;
				padding-bottom: 10px;
				border-bottom: 1px solid #ebedf2;
			}
			.professional-hr-entry__metric:last-child {
				border-bottom: 0;
				padding-bottom: 0;
			}
			.professional-hr-entry__form-grid {
				display: grid;
				grid-template-columns: repeat(2, minmax(0, 1fr));
				gap: 14px 16px;
			}
			.professional-hr-entry__form-grid .frappe-control {
				margin-bottom: 0;
			}
			.professional-hr-entry__actions {
				display: flex;
				gap: 10px;
				flex-wrap: wrap;
				margin-top: 18px;
			}
			.professional-hr-entry__button {
				min-height: 42px;
				border: 1px solid #1f6f4a;
				border-radius: 8px;
				padding: 9px 14px;
				font-size: 13px;
				font-weight: 700;
				color: #ffffff;
				background: #1f6f4a;
				cursor: pointer;
			}
			.professional-hr-entry__button--secondary {
				color: #123326;
				background: #eef7f1;
				border-color: #b7dfc7;
			}
			.professional-hr-entry__empty {
				padding: 18px;
				border: 1px dashed #c9d1dd;
				border-radius: 8px;
				color: #5e6c84;
			}
			@media (max-width: 900px) {
				.professional-hr-entry__hero,
				.professional-hr-entry__form-grid {
					grid-template-columns: 1fr;
				}
			}
		`;
		document.head.appendChild(style);
	}

	renderLoading() {
		this.page.body.html(`<div class="professional-hr-entry"><section class="professional-hr-entry__panel">${__("Loading professional entry form...")}</section></div>`);
	}

	getFeatureId() {
		return frappe.get_route()?.[1] || new URLSearchParams(window.location.search).get("feature") || "";
	}

	loadEntry() {
		const featureId = this.getFeatureId();
		this.renderLoading();
		frappe.call({
			method: "hr_suite.hr_suite.professional_hr_catalog.get_professional_hr_feature",
			args: { feature_id: featureId },
			callback: (response) => {
				this.feature = response.message?.feature;
				if (!this.feature || this.feature.target_type !== "DocType") {
					this.renderUnavailable();
					return;
				}
				this.loadDocTypeMeta(this.feature.target);
			},
			error: () => this.renderUnavailable(),
		});
	}

	loadDocTypeMeta(doctype) {
		frappe.model.with_doctype(doctype, () => {
			const meta = frappe.get_meta(doctype);
			if (!meta) {
				this.renderUnavailable();
				return;
			}
			this.renderForm(meta);
		});
	}

	renderUnavailable() {
		this.page.body.html(`
			<div class="professional-hr-entry">
				<section class="professional-hr-entry__panel">
					<div class="professional-hr-entry__eyebrow">${__("Professional Entry")}</div>
					<h2 class="professional-hr-entry__title">${__("Entry form is not available for this feature")}</h2>
					<p class="professional-hr-entry__text">${__("This feature is a report, page, or external route. Use its professional feature page or ERPNext view instead.")}</p>
					<div class="professional-hr-entry__actions">
						<button class="professional-hr-entry__button" data-route="/app/professional-hr-hub">${__("Back to Hub")}</button>
					</div>
				</section>
			</div>
		`);
		this.bindRoutes();
	}

	renderForm(meta) {
		this.controls = [];
		this.page.set_title(__(`New ${this.feature.title}`));
		this.page.body.html(`
			<div class="professional-hr-entry">
				<section class="professional-hr-entry__hero">
					<div class="professional-hr-entry__panel">
						<div class="professional-hr-entry__eyebrow">${__("Professional Entry")}</div>
						<h2 class="professional-hr-entry__title">${frappe.utils.escape_html(__(this.feature.title))}</h2>
						<p class="professional-hr-entry__text">${frappe.utils.escape_html(__(this.feature.summary || ""))}</p>
						<p class="professional-hr-entry__text">${frappe.utils.escape_html(this.feature.summary_ar || "")}</p>
					</div>
					<div class="professional-hr-entry__panel">
						<div class="professional-hr-entry__metrics">
							<div class="professional-hr-entry__metric"><span>${__("DocType")}</span><strong>${frappe.utils.escape_html(meta.name)}</strong></div>
							<div class="professional-hr-entry__metric"><span>${__("Mode")}</span><strong>${__("Focused Entry")}</strong></div>
							<div class="professional-hr-entry__metric"><span>${__("Full Form")}</span><strong>${__("Available")}</strong></div>
						</div>
					</div>
				</section>
				<section class="professional-hr-entry__panel">
					<div class="professional-hr-entry__form-grid" data-form-grid></div>
					<div class="professional-hr-entry__actions">
						<button class="professional-hr-entry__button" data-save>${__("Save Entry")}</button>
						<button class="professional-hr-entry__button professional-hr-entry__button--secondary" data-route="${frappe.utils.escape_html(this.feature.route)}/new">${__("Open Full ERPNext Form")}</button>
						<button class="professional-hr-entry__button professional-hr-entry__button--secondary" data-route="${frappe.utils.escape_html(this.feature.detail_route)}">${__("Back to Feature")}</button>
					</div>
				</section>
			</div>
		`);
		this.renderControls(meta);
		this.page.body.find("[data-save]").on("click", () => this.saveEntry(meta.name));
		this.bindRoutes();
	}

	renderControls(meta) {
		const fields = this.getEntryFields(meta);
		const grid = this.page.body.find("[data-form-grid]");
		if (!fields.length) {
			grid.html(`<div class="professional-hr-entry__empty">${__("No quick-entry fields are available for this DocType. Open the full ERPNext form.")}</div>`);
			return;
		}
		fields.forEach((field) => {
			const controlWrapper = $('<div class="professional-hr-entry__field"></div>').appendTo(grid);
			const control = frappe.ui.form.make_control({
				df: { ...field, placeholder: field.label },
				parent: controlWrapper,
				only_input: false,
				render_input: true,
			});
			control.refresh();
			controlWrapper.find(".has-error").removeClass("has-error");
			controlWrapper.find(".is-invalid").removeClass("is-invalid");
			this.controls.push(control);
		});
	}

	getEntryFields(meta) {
		const allowedTypes = new Set(["Data", "Link", "Dynamic Link", "Select", "Date", "Datetime", "Time", "Currency", "Float", "Int", "Percent", "Check", "Small Text", "Text", "Long Text"]);
		const excluded = new Set(["name", "owner", "creation", "modified", "modified_by", "docstatus", "idx", "amended_from"]);
		const fields = (meta.fields || []).filter((field) => {
			return allowedTypes.has(field.fieldtype)
				&& field.fieldname
				&& !excluded.has(field.fieldname)
				&& !field.read_only
				&& !field.hidden
				&& !field.depends_on;
		});
		const required = fields.filter((field) => field.reqd);
		const useful = fields.filter((field) => !field.reqd).slice(0, 10);
		return [...required, ...useful].slice(0, 16);
	}

	saveEntry(doctype) {
		const doc = { doctype };
		for (const control of this.controls) {
			const value = control.get_value();
			if (value !== undefined && value !== null && value !== "") {
				doc[control.df.fieldname] = value;
			}
		}
		frappe.call({
			method: "frappe.client.insert",
			args: { doc },
			freeze: true,
			freeze_message: __("Saving entry..."),
			callback: (response) => {
				const saved = response.message;
				frappe.show_alert({ message: __("Entry saved"), indicator: "green" });
				if (saved?.doctype && saved?.name) {
					frappe.set_route("Form", saved.doctype, saved.name);
				}
			},
		});
	}

	bindRoutes() {
		this.page.body.find("[data-route]").on("click", (event) => this.open(event.currentTarget.dataset.route));
	}

	open(route) {
		if (route.startsWith("/app/")) {
			frappe.set_route(route.slice(5).split("/"));
			return;
		}
		if (route.startsWith("/")) {
			window.location.href = route;
			return;
		}
		frappe.set_route(route);
	}
};
