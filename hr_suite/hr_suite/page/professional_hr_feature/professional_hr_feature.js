frappe.provide("hr_suite");

hr_suite.PROFESSIONAL_HR_CATALOG_VERSION = "2026-05-08-component-parent-routes";

frappe.pages["professional-hr-feature"].on_page_load = function (wrapper) {
	wrapper.professional_hr_feature = new hr_suite.ProfessionalHrFeature(wrapper);
};

frappe.pages["professional-hr-feature"].on_page_show = function (wrapper) {
	wrapper.professional_hr_feature?.loadFeature();
};

hr_suite.ProfessionalHrFeature = class ProfessionalHrFeature {
	constructor(wrapper) {
		this.wrapper = wrapper;
		this.page = frappe.ui.make_app_page({
			parent: wrapper,
			title: __("Professional HR Feature"),
			single_column: true,
		});
		this.ensureStyles();
		this.renderLoading();
		this.loadFeature();
		this.page.set_primary_action(__("Professional HR Hub"), () => this.open("/app/professional-hr-hub"));
	}

	ensureStyles() {
		if (document.getElementById("professional-hr-feature-style")) {
			return;
		}

		const style = document.createElement("style");
		style.id = "professional-hr-feature-style";
		style.textContent = `
			.professional-hr-feature {
				display: grid;
				gap: 18px;
				padding: 8px 0 30px;
				color: #172b4d;
			}

			.professional-hr-feature__panel,
			.professional-hr-feature__step,
			.professional-hr-feature__related {
				background: #ffffff;
				border: 1px solid #dfe3eb;
				border-radius: 8px;
				box-shadow: 0 8px 24px rgba(23, 43, 77, 0.06);
			}

			.professional-hr-feature__panel {
				padding: 22px;
			}

			.professional-hr-feature__hero {
				display: grid;
				grid-template-columns: minmax(0, 1.35fr) minmax(280px, 0.65fr);
				gap: 14px;
			}

			.professional-hr-feature__eyebrow,
			.professional-hr-feature__label {
				font-size: 12px;
				font-weight: 700;
				text-transform: uppercase;
				color: #216e4e;
			}

			.professional-hr-feature__title {
				font-size: 28px;
				font-weight: 700;
				line-height: 1.25;
				margin: 6px 0 8px;
			}

			.professional-hr-feature__arabic {
				font-size: 16px;
				font-weight: 700;
				color: #344563;
				margin-bottom: 10px;
			}

			.professional-hr-feature__text,
			.professional-hr-feature__muted {
				font-size: 13px;
				line-height: 1.65;
				color: #5e6c84;
				margin: 0;
			}

			.professional-hr-feature__actions,
			.professional-hr-feature__grid,
			.professional-hr-feature__related-grid {
				display: grid;
				gap: 10px;
			}

			.professional-hr-feature__actions {
				grid-template-columns: repeat(2, minmax(0, 1fr));
				margin-top: 18px;
			}

			.professional-hr-feature__grid,
			.professional-hr-feature__related-grid {
				grid-template-columns: repeat(3, minmax(0, 1fr));
			}

			.professional-hr-feature__button {
				min-height: 42px;
				border: 1px solid #1f6f4a;
				border-radius: 8px;
				padding: 9px 12px;
				font-size: 13px;
				font-weight: 700;
				color: #ffffff;
				background: #1f6f4a;
				cursor: pointer;
			}

			.professional-hr-feature__button--secondary {
				color: #123326;
				background: #eef7f1;
				border-color: #b7dfc7;
			}

			.professional-hr-feature__metric {
				display: flex;
				justify-content: space-between;
				gap: 12px;
				padding-bottom: 10px;
				border-bottom: 1px solid #ebedf2;
			}

			.professional-hr-feature__metric:last-child {
				border-bottom: 0;
				padding-bottom: 0;
			}

			.professional-hr-feature__step,
			.professional-hr-feature__related {
				padding: 14px;
			}

			.professional-hr-feature__step-title,
			.professional-hr-feature__related-title {
				font-size: 14px;
				font-weight: 700;
				margin-bottom: 5px;
			}

			.professional-hr-feature__related {
				cursor: pointer;
				transition: border-color 0.15s ease, transform 0.15s ease, box-shadow 0.15s ease;
			}

			.professional-hr-feature__related:hover,
			.professional-hr-feature__button:hover {
				border-color: #1f6f4a;
				box-shadow: 0 10px 24px rgba(31, 111, 74, 0.12);
				transform: translateY(-1px);
			}

			@media (max-width: 900px) {
				.professional-hr-feature__hero,
				.professional-hr-feature__grid,
				.professional-hr-feature__related-grid,
				.professional-hr-feature__actions {
					grid-template-columns: 1fr;
				}
			}
		`;
		document.head.appendChild(style);
	}

	renderLoading() {
		this.page.body.html(`<div class="professional-hr-feature"><section class="professional-hr-feature__panel">${__("Loading feature page...")}</section></div>`);
	}

	loadFeature() {
		const featureId = this.getFeatureId();
		const cached = this.getCachedFeatureData(featureId);
		if (cached) {
			this.renderFeature(cached);
		} else {
			this.renderLoading();
		}
		frappe.call({
			method: "hr_suite.hr_suite.professional_hr_catalog.get_professional_hr_feature",
			args: { feature_id: featureId },
			callback: (response) => this.renderFeature(response.message),
			error: () => {
				if (cached) {
					return;
				}
				this.page.body.html(`<div class="professional-hr-feature"><section class="professional-hr-feature__panel">${__("Feature page not found.")}</section></div>`);
			},
		});
	}

	getFeatureId() {
		return frappe.get_route()?.[1] || new URLSearchParams(window.location.search).get("feature") || "mobile-attendance";
	}

	getCachedFeatureData(featureId) {
		try {
			const catalog = JSON.parse(localStorage.getItem("professional_hr_catalog") || "{}");
			if (catalog.version !== hr_suite.PROFESSIONAL_HR_CATALOG_VERSION) {
				return null;
			}
			const feature = (catalog.features || []).find((item) => item.id === featureId);
			if (!feature) {
				return null;
			}
			const category = (catalog.categories || []).find((item) => item.id === feature.category) || null;
			const related = (catalog.features || [])
				.filter((item) => item.category === feature.category && item.id !== feature.id)
				.slice(0, 6);
			return {
				feature,
				category,
				related,
				catalog_summary: {
					total_features: catalog.total_features || (catalog.features || []).length,
					category_features: category?.count || related.length + 1,
				},
			};
		} catch (error) {
			return null;
		}
	}

	renderFeature(data) {
		const feature = data.feature;
		const category = data.category || {};
		const actionLabel = feature.action_label || "Open ERPNext View";
		this.page.set_title(__(feature.title));
		this.page.body.html(`
			<div class="professional-hr-feature">
				<section class="professional-hr-feature__hero">
					<div class="professional-hr-feature__panel">
						<div class="professional-hr-feature__eyebrow">${frappe.utils.escape_html(__(category.title || "Hr Suite"))}</div>
						<h2 class="professional-hr-feature__title">${frappe.utils.escape_html(__(feature.title))}</h2>
						<div class="professional-hr-feature__arabic">${frappe.utils.escape_html(feature.title_ar || "")}</div>
						<p class="professional-hr-feature__text">${frappe.utils.escape_html(__(feature.summary))}</p>
						<p class="professional-hr-feature__text">${frappe.utils.escape_html(feature.summary_ar || "")}</p>
						<div class="professional-hr-feature__actions">
							${feature.entry_route ? `<button class="professional-hr-feature__button" data-route="${frappe.utils.escape_html(feature.entry_route)}">${__("Create Professional Entry")}</button>` : ""}
							<button class="professional-hr-feature__button" data-route="${frappe.utils.escape_html(feature.route)}">${frappe.utils.escape_html(__(actionLabel))}</button>
							<button class="professional-hr-feature__button professional-hr-feature__button--secondary" data-route="/app/professional-hr-hub">${__("Back to Hub")}</button>
						</div>
					</div>
					<div class="professional-hr-feature__panel">
						<div class="professional-hr-feature__metric"><span>${__("Type")}</span><strong>${frappe.utils.escape_html(__(feature.target_type))}</strong></div>
						<div class="professional-hr-feature__metric"><span>${__("Area")}</span><strong>${frappe.utils.escape_html(__(category.title || ""))}</strong></div>
						<div class="professional-hr-feature__metric"><span>${__("Area Features")}</span><strong>${frappe.utils.escape_html(String(data.catalog_summary.category_features || 0))}</strong></div>
						<div class="professional-hr-feature__metric"><span>${__("Catalog")}</span><strong>${frappe.utils.escape_html(String(data.catalog_summary.total_features || 0))}</strong></div>
					</div>
				</section>

				<section class="professional-hr-feature__panel">
					<div class="professional-hr-feature__grid">
						${this.getOperatingSteps(feature).map((step) => `
							<div class="professional-hr-feature__step">
								<div class="professional-hr-feature__label">${frappe.utils.escape_html(__(step.label))}</div>
								<div class="professional-hr-feature__step-title">${frappe.utils.escape_html(__(step.title))}</div>
								<p class="professional-hr-feature__muted">${frappe.utils.escape_html(__(step.note))}</p>
							</div>
						`).join("")}
					</div>
				</section>

				<section class="professional-hr-feature__panel">
					<div class="professional-hr-feature__eyebrow">${__("Related Features")}</div>
					<div class="professional-hr-feature__related-grid">
						${data.related.map((item) => `
							<div class="professional-hr-feature__related" data-route="${frappe.utils.escape_html(item.detail_route)}">
								<div class="professional-hr-feature__related-title">${frappe.utils.escape_html(__(item.title))}</div>
								<p class="professional-hr-feature__muted">${frappe.utils.escape_html(item.title_ar || "")}</p>
							</div>
						`).join("")}
					</div>
				</section>
			</div>
		`);

		this.page.body.find("[data-route]").on("click", (event) => this.open(event.currentTarget.dataset.route));
	}

	getOperatingSteps(feature) {
		return [
			{ label: "Purpose", title: "What this page is for", note: feature.summary },
			{ label: "Workflow", title: "Recommended operating rhythm", note: "Review records, handle exceptions, approve pending items, then use the linked ERPNext view for final transactions." },
			{ label: "Controls", title: "Governance lens", note: "Use this professional page as the entry point, then keep audit-grade data in the underlying DocType, Report, Page, or URL." },
		];
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
