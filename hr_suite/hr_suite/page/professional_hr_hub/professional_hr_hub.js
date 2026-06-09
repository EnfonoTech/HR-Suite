frappe.provide("hr_suite");

frappe.pages["professional-hr-hub"].on_page_load = function (wrapper) {
	new hr_suite.ProfessionalHrHub(wrapper);
};

hr_suite.ProfessionalHrHub = class ProfessionalHrHub {
	constructor(wrapper) {
		this.wrapper = wrapper;
		this.catalog = { categories: [], features: [] };
		this.activeCategory = "all";
		this.searchText = "";
		this.page = frappe.ui.make_app_page({
			parent: wrapper,
			title: __("Professional HR Hub"),
			single_column: true,
		});
		this.ensureStyles();
		this.renderShell();
		this.loadCatalog();
		this.page.set_primary_action(__("Mobile Attendance"), () => this.open("/mobile-attendance"));
		this.page.add_menu_item(__("Hr Suite Workspace"), () => this.open("/app/saudi-hr"));
		this.page.add_menu_item(__("Hr Suite Settings"), () => this.open("/app/saudi-hr-settings/Hr Suite Settings"));
	}

	ensureStyles() {
		if (document.getElementById("professional-hr-hub-style")) {
			return;
		}

		const style = document.createElement("style");
		style.id = "professional-hr-hub-style";
		style.textContent = `
			.professional-hr-hub {
				display: grid;
				gap: 18px;
				padding: 8px 0 30px;
				color: #172b4d;
			}

			.professional-hr-hub__panel,
			.professional-hr-hub__feature,
			.professional-hr-hub__category {
				background: #ffffff;
				border: 1px solid #dfe3eb;
				border-radius: 8px;
				box-shadow: 0 8px 24px rgba(23, 43, 77, 0.06);
			}

			.professional-hr-hub__panel {
				padding: 20px;
			}

			.professional-hr-hub__hero {
				display: grid;
				grid-template-columns: minmax(0, 1.35fr) minmax(300px, 0.65fr);
				gap: 14px;
			}

			.professional-hr-hub__eyebrow {
				font-size: 12px;
				font-weight: 700;
				text-transform: uppercase;
				color: #216e4e;
				margin-bottom: 8px;
			}

			.professional-hr-hub__title {
				font-size: 26px;
				font-weight: 700;
				line-height: 1.25;
				margin: 0 0 8px;
			}

			.professional-hr-hub__subtitle,
			.professional-hr-hub__muted,
			.professional-hr-hub__feature-note,
			.professional-hr-hub__category-note {
				font-size: 13px;
				line-height: 1.6;
				color: #5e6c84;
				margin: 0;
			}

			.professional-hr-hub__stats {
				display: grid;
				gap: 10px;
			}

			.professional-hr-hub__stat {
				display: flex;
				justify-content: space-between;
				gap: 12px;
				padding-bottom: 10px;
				border-bottom: 1px solid #ebedf2;
			}

			.professional-hr-hub__stat:last-child {
				border-bottom: 0;
				padding-bottom: 0;
			}

			.professional-hr-hub__stat-label {
				font-size: 12px;
				color: #5e6c84;
			}

			.professional-hr-hub__stat-value {
				font-size: 14px;
				font-weight: 700;
				text-align: end;
			}

			.professional-hr-hub__toolbar {
				display: grid;
				grid-template-columns: minmax(260px, 1fr) auto;
				gap: 10px;
				align-items: center;
			}

			.professional-hr-hub__search {
				width: 100%;
				min-height: 40px;
				border: 1px solid #dfe3eb;
				border-radius: 8px;
				padding: 9px 12px;
				font-size: 13px;
				background: #f7f9fb;
			}

			.professional-hr-hub__button {
				min-height: 40px;
				display: inline-flex;
				align-items: center;
				justify-content: center;
				padding: 9px 12px;
				border: 1px solid #1f6f4a;
				border-radius: 8px;
				font-size: 13px;
				font-weight: 700;
				color: #ffffff;
				background: #1f6f4a;
				cursor: pointer;
			}

			.professional-hr-hub__category-grid,
			.professional-hr-hub__feature-grid {
				display: grid;
				gap: 10px;
			}

			.professional-hr-hub__category-grid {
				grid-template-columns: repeat(4, minmax(0, 1fr));
			}

			.professional-hr-hub__feature-grid {
				grid-template-columns: repeat(3, minmax(0, 1fr));
			}

			.professional-hr-hub__category,
			.professional-hr-hub__feature {
				transition: border-color 0.15s ease, transform 0.15s ease, box-shadow 0.15s ease;
			}

			.professional-hr-hub__category {
				padding: 13px;
				cursor: pointer;
			}

			.professional-hr-hub__feature {
				display: grid;
				gap: 10px;
				min-height: 170px;
				padding: 14px;
			}

			.professional-hr-hub__category.is-active,
			.professional-hr-hub__category:hover,
			.professional-hr-hub__feature:hover {
				border-color: #1f6f4a;
				box-shadow: 0 10px 24px rgba(31, 111, 74, 0.12);
				transform: translateY(-1px);
			}

			.professional-hr-hub__category-title,
			.professional-hr-hub__feature-title {
				font-size: 14px;
				font-weight: 700;
				margin-bottom: 5px;
				color: #172b4d;
			}

			.professional-hr-hub__feature-meta,
			.professional-hr-hub__feature-actions {
				display: flex;
				gap: 8px;
				align-items: center;
			}

			.professional-hr-hub__feature-meta {
				justify-content: space-between;
			}

			.professional-hr-hub__feature-actions {
				margin-top: auto;
			}

			.professional-hr-hub__badge {
				display: inline-flex;
				align-items: center;
				min-height: 22px;
				padding: 3px 8px;
				border-radius: 999px;
				font-size: 11px;
				font-weight: 700;
				background: #eef7f1;
				color: #216e4e;
			}

			.professional-hr-hub__link {
				border: 0;
				background: transparent;
				padding: 0;
				font-size: 12px;
				font-weight: 700;
				color: #1f6f4a;
				cursor: pointer;
			}

			.professional-hr-hub__empty {
				padding: 22px;
				text-align: center;
				border: 1px dashed #c9d1dd;
				border-radius: 8px;
				color: #5e6c84;
			}

			@media (max-width: 1100px) {
				.professional-hr-hub__category-grid,
				.professional-hr-hub__feature-grid {
					grid-template-columns: repeat(2, minmax(0, 1fr));
				}
			}

			@media (max-width: 760px) {
				.professional-hr-hub__hero,
				.professional-hr-hub__toolbar,
				.professional-hr-hub__category-grid,
				.professional-hr-hub__feature-grid {
					grid-template-columns: 1fr;
				}

				.professional-hr-hub__title {
					font-size: 22px;
				}
			}
		`;
		document.head.appendChild(style);
	}

	renderShell() {
		this.page.body.html(`
			<div class="professional-hr-hub">
				<section class="professional-hr-hub__hero">
					<div class="professional-hr-hub__panel">
						<div class="professional-hr-hub__eyebrow">Hr Suite</div>
						<h2 class="professional-hr-hub__title">${__("Professional HR Hub")}</h2>
						<p class="professional-hr-hub__subtitle">${__("A complete Hr Suite operating catalog with dedicated professional pages for every feature, while the default ERPNext screens remain available when needed.")}</p>
					</div>
					<div class="professional-hr-hub__panel">
						<div class="professional-hr-hub__eyebrow">${__("Coverage")}</div>
						<div class="professional-hr-hub__stats" data-stats></div>
					</div>
				</section>

				<section class="professional-hr-hub__panel">
					<div class="professional-hr-hub__toolbar">
						<input class="professional-hr-hub__search" data-search placeholder="${frappe.utils.escape_html(__("Search features, reports, workflows, leave, payroll, compliance..."))}">
						<button class="professional-hr-hub__button" data-route="/mobile-attendance">${__("Mobile Attendance")}</button>
					</div>
				</section>

				<section class="professional-hr-hub__panel">
					<div class="professional-hr-hub__category-grid" data-categories></div>
				</section>

				<section class="professional-hr-hub__panel">
					<div class="professional-hr-hub__feature-grid" data-features></div>
				</section>
			</div>
		`);

		this.page.body.find("[data-search]").on("input", (event) => {
			this.searchText = event.currentTarget.value.trim().toLowerCase();
			this.renderFeatures();
		});

		this.page.body.find("[data-route]").on("click", (event) => {
			this.open(event.currentTarget.dataset.route);
		});
	}

	loadCatalog() {
		this.page.body.find("[data-features]").html(`<div class="professional-hr-hub__empty">${__("Loading Hr Suite features...")}</div>`);
		frappe.call({
			method: "hr_suite.hr_suite.professional_hr_catalog.get_professional_hr_catalog",
			callback: (response) => {
				this.catalog = response.message || { categories: [], features: [] };
				this.cacheCatalog();
				this.renderStats();
				this.renderCategories();
				this.renderFeatures();
			},
			error: () => {
				this.page.body.find("[data-features]").html(`<div class="professional-hr-hub__empty">${__("Unable to load the feature catalog.")}</div>`);
			},
		});
	}

	cacheCatalog() {
		try {
			localStorage.setItem("professional_hr_catalog", JSON.stringify(this.catalog));
		} catch (error) {
		}
	}

	renderStats() {
		const stats = [
			{ label: "Feature Pages", value: this.catalog.total_features || this.catalog.features.length },
			{ label: "Operating Areas", value: this.catalog.categories.length },
			{ label: "Primary Actions", value: this.catalog.primary_features || 0 },
			{ label: "Navigation", value: "Custom first, ERPNext ready" },
		];

		this.page.body.find("[data-stats]").html(stats.map((stat) => `
			<div class="professional-hr-hub__stat">
				<div class="professional-hr-hub__stat-label">${frappe.utils.escape_html(__(stat.label))}</div>
				<div class="professional-hr-hub__stat-value">${frappe.utils.escape_html(__(String(stat.value)))}</div>
			</div>
		`).join(""));
	}

	renderCategories() {
		const categories = [{ id: "all", title: "All Features", title_ar: "", count: this.catalog.features.length }, ...this.catalog.categories];
		this.page.body.find("[data-categories]").html(categories.map((category) => `
			<div class="professional-hr-hub__category ${this.activeCategory === category.id ? "is-active" : ""}" data-category="${frappe.utils.escape_html(category.id)}">
				<div class="professional-hr-hub__category-title">${frappe.utils.escape_html(__(category.title))}</div>
				<p class="professional-hr-hub__category-note">${frappe.utils.escape_html(category.title_ar || "")}</p>
				<span class="professional-hr-hub__badge">${frappe.utils.escape_html(String(category.count || 0))}</span>
			</div>
		`).join(""));

		this.page.body.find("[data-category]").on("click", (event) => {
			this.activeCategory = event.currentTarget.dataset.category;
			this.renderCategories();
			this.renderFeatures();
		});
	}

	renderFeatures() {
		const filtered = this.catalog.features.filter((feature) => {
			const categoryMatch = this.activeCategory === "all" || feature.category === this.activeCategory;
			const haystack = [feature.title, feature.title_ar, feature.summary, feature.summary_ar, feature.target_type, feature.target].join(" ").toLowerCase();
			return categoryMatch && (!this.searchText || haystack.includes(this.searchText));
		});

		if (!filtered.length) {
			this.page.body.find("[data-features]").html(`<div class="professional-hr-hub__empty">${__("No matching features found.")}</div>`);
			return;
		}

		this.page.body.find("[data-features]").html(filtered.map((feature) => `
			<article class="professional-hr-hub__feature">
				<div class="professional-hr-hub__feature-meta">
					<span class="professional-hr-hub__badge">${frappe.utils.escape_html(__(feature.target_type))}</span>
					${feature.priority ? `<span class="professional-hr-hub__badge">${frappe.utils.escape_html(__(feature.priority))}</span>` : ""}
				</div>
				<div>
					<div class="professional-hr-hub__feature-title">${frappe.utils.escape_html(__(feature.title))}</div>
					<p class="professional-hr-hub__feature-note">${frappe.utils.escape_html(feature.title_ar || "")}</p>
				</div>
				<p class="professional-hr-hub__feature-note">${frappe.utils.escape_html(__(feature.summary))}</p>
				<div class="professional-hr-hub__feature-actions">
					<button class="professional-hr-hub__link" data-feature-id="${frappe.utils.escape_html(feature.id)}">${__("Open Feature Page")}</button>
					<button class="professional-hr-hub__link" data-route="${frappe.utils.escape_html(feature.route)}">${frappe.utils.escape_html(__(feature.action_label || "ERPNext View"))}</button>
				</div>
			</article>
		`).join(""));

		this.page.body.find("[data-feature-id]").on("click", (event) => this.openFeature(event.currentTarget.dataset.featureId));
		this.page.body.find("[data-route]").on("click", (event) => this.open(event.currentTarget.dataset.route));
	}

	openFeature(featureId) {
		const feature = this.catalog.features.find((item) => item.id === featureId);
		if (feature) {
			try {
				localStorage.setItem("professional_hr_selected_feature_id", featureId);
			} catch (error) {
			}
			this.open(feature.detail_route);
		}
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
