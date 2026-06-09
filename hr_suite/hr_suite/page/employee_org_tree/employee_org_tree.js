frappe.provide("hr_suite");

frappe.pages["employee-org-tree"].on_page_load = function (wrapper) {
	new hr_suite.EmployeeOrgTree(wrapper);
};

hr_suite.EmployeeOrgTree = class EmployeeOrgTree {
	constructor(wrapper) {
		this.wrapper = wrapper;
		this.summary = null;
		this.ensureStyles();
		this.page = frappe.ui.make_app_page({
			parent: wrapper,
			title: __("Employee Org Tree"),
			single_column: true,
		});
		this.makeFilters();
		this.makeLayout();
		this.page.set_primary_action(__("Refresh"), () => this.refresh());
		this.page.add_menu_item(__("Expand All"), () => this.expandAll());
		this.refresh();
	}

	ensureStyles() {
		if (document.getElementById("employee-org-tree-style")) {
			return;
		}

		const style = document.createElement("style");
		style.id = "employee-org-tree-style";
		style.textContent = `
			.employee-org-tree {
				display: grid;
				gap: 18px;
				padding: 8px 0 28px;
			}

			.employee-org-tree__hero {
				display: grid;
				grid-template-columns: minmax(0, 1.7fr) minmax(280px, 1fr);
				gap: 16px;
			}

			.employee-org-tree__panel,
			.employee-org-tree__card,
			.employee-org-tree__detail {
				background: linear-gradient(180deg, #fffef8 0%, #f6f2e7 100%);
				border: 1px solid #e2d7b8;
				border-radius: 20px;
				box-shadow: 0 12px 30px rgba(93, 70, 27, 0.08);
			}

			.employee-org-tree__panel {
				padding: 22px;
			}

			.employee-org-tree__eyebrow {
				font-size: 12px;
				font-weight: 700;
				letter-spacing: 0.08em;
				text-transform: uppercase;
				color: #8f6b22;
				margin-bottom: 8px;
			}

			.employee-org-tree__title {
				font-size: 28px;
				line-height: 1.2;
				font-weight: 700;
				color: #3c2d11;
				margin: 0 0 10px;
			}

			.employee-org-tree__subtitle {
				font-size: 14px;
				line-height: 1.8;
				color: #6e5a36;
				margin: 0;
			}

			.employee-org-tree__scope {
				display: inline-flex;
				align-items: center;
				padding: 8px 12px;
				margin-top: 14px;
				border-radius: 999px;
				background: #f4ead2;
				color: #6a511e;
				font-size: 12px;
				font-weight: 700;
			}

			.employee-org-tree__metrics {
				display: grid;
				grid-template-columns: repeat(2, minmax(0, 1fr));
				gap: 12px;
			}

			.employee-org-tree__card {
				padding: 16px;
			}

			.employee-org-tree__metric-label {
				font-size: 12px;
				font-weight: 600;
				color: #7a6440;
				margin-bottom: 6px;
			}

			.employee-org-tree__metric-value {
				font-size: 30px;
				font-weight: 700;
				color: #3c2d11;
			}

			.employee-org-tree__body {
				display: grid;
				grid-template-columns: minmax(0, 1.45fr) minmax(320px, 0.9fr);
				gap: 16px;
			}

			.employee-org-tree__tree-panel,
			.employee-org-tree__detail-panel {
				padding: 20px;
			}

			.employee-org-tree__panel-title {
				font-size: 20px;
				font-weight: 700;
				color: #3c2d11;
				margin: 0 0 6px;
			}

			.employee-org-tree__panel-subtitle {
				font-size: 13px;
				color: #7a6440;
				margin: 0 0 16px;
			}

			.employee-org-tree__tree-host {
				min-height: 440px;
				padding: 8px 2px 0;
			}

			.employee-org-tree__tree-host .tree {
				background: rgba(255, 255, 255, 0.55);
				border-radius: 16px;
				padding: 10px 14px;
			}

			.employee-org-tree__node {
				display: inline-flex;
				align-items: center;
				gap: 8px;
				flex-wrap: wrap;
			}

			.employee-org-tree__badge {
				display: inline-flex;
				align-items: center;
				padding: 3px 8px;
				border-radius: 999px;
				font-size: 11px;
				font-weight: 700;
			}

			.employee-org-tree__badge--department {
				background: #efe1bb;
				color: #6a511e;
			}

			.employee-org-tree__badge--employee {
				background: #e2efe5;
				color: #1f5d36;
			}

			.employee-org-tree__node-title {
				font-weight: 700;
				color: #35260f;
			}

			.employee-org-tree__node-meta {
				font-size: 12px;
				color: #7a6440;
			}

			.employee-org-tree__detail-grid {
				display: grid;
				gap: 10px;
			}

			.employee-org-tree__detail {
				padding: 12px 14px;
			}

			.employee-org-tree__detail-label {
				font-size: 12px;
				font-weight: 700;
				color: #7a6440;
				margin-bottom: 4px;
			}

			.employee-org-tree__detail-value {
				font-size: 14px;
				color: #3c2d11;
				font-weight: 600;
			}

			.employee-org-tree__empty {
				padding: 18px;
				border: 1px dashed #d3c29a;
				border-radius: 16px;
				background: rgba(255, 255, 255, 0.6);
				font-size: 14px;
				color: #7a6440;
			}

			@media (max-width: 980px) {
				.employee-org-tree__hero,
				.employee-org-tree__body {
					grid-template-columns: 1fr;
				}
			}
		`;
		document.head.appendChild(style);
	}

	makeFilters() {
		[
			{
				fieldname: "company",
				fieldtype: "Link",
				label: __("Company"),
				options: "Company",
				change: () => this.refresh(),
			},
			{
				fieldname: "branch",
				fieldtype: "Link",
				label: __("Branch"),
				options: "Branch",
				change: () => this.refresh(),
			},
			{
				fieldname: "department",
				fieldtype: "Link",
				label: __("Department"),
				options: "Department",
				change: () => this.refresh(),
			},
		].forEach((field) => this.page.add_field(field));
	}

	makeLayout() {
		this.page.body.html(`
			<div class="employee-org-tree">
				<section class="employee-org-tree__hero">
					<div class="employee-org-tree__panel">
						<div class="employee-org-tree__eyebrow">Hr Suite</div>
						<h1 class="employee-org-tree__title">${__("Employee reporting tree with department context")}</h1>
						<p class="employee-org-tree__subtitle">${__("Track how employees relate to their departments, direct managers, and approval references without leaving the Desk.")}</p>
						<div class="employee-org-tree__scope" data-org-tree-scope>${__("Loading scope...")}</div>
					</div>
					<div class="employee-org-tree__metrics">
						<div class="employee-org-tree__card">
							<div class="employee-org-tree__metric-label">${__("Employees")}</div>
							<div class="employee-org-tree__metric-value" data-org-tree-employees>--</div>
						</div>
						<div class="employee-org-tree__card">
							<div class="employee-org-tree__metric-label">${__("Departments")}</div>
							<div class="employee-org-tree__metric-value" data-org-tree-departments>--</div>
						</div>
						<div class="employee-org-tree__card">
							<div class="employee-org-tree__metric-label">${__("Managers")}</div>
							<div class="employee-org-tree__metric-value" data-org-tree-managers>--</div>
						</div>
						<div class="employee-org-tree__card">
							<div class="employee-org-tree__metric-label">${__("Approver references")}</div>
							<div class="employee-org-tree__metric-value" data-org-tree-approvers>--</div>
						</div>
					</div>
				</section>
				<section class="employee-org-tree__body">
					<div class="employee-org-tree__panel employee-org-tree__tree-panel">
						<h2 class="employee-org-tree__panel-title">${__("Hierarchy")}</h2>
						<p class="employee-org-tree__panel-subtitle">${__("Departments are the first level, then employees expand through their direct in-department reporting lines.")}</p>
						<div class="employee-org-tree__tree-host" data-org-tree-host></div>
					</div>
					<div class="employee-org-tree__panel employee-org-tree__detail-panel">
						<h2 class="employee-org-tree__panel-title">${__("Node details")}</h2>
						<p class="employee-org-tree__panel-subtitle">${__("Select any department or employee to inspect its references and approvers.")}</p>
						<div data-org-tree-detail class="employee-org-tree__empty">${__("Select a node from the tree to inspect it here.")}</div>
					</div>
				</section>
			</div>
		`);

		this.scopeEl = this.page.body.find("[data-org-tree-scope]");
		this.employeeCountEl = this.page.body.find("[data-org-tree-employees]");
		this.departmentCountEl = this.page.body.find("[data-org-tree-departments]");
		this.managerCountEl = this.page.body.find("[data-org-tree-managers]");
		this.approverCountEl = this.page.body.find("[data-org-tree-approvers]");
		this.treeHost = this.page.body.find("[data-org-tree-host]");
		this.detailEl = this.page.body.find("[data-org-tree-detail]");
	}

	getFilters() {
		return {
			company: this.page.fields_dict.company.get_value(),
			branch: this.page.fields_dict.branch.get_value(),
			department: this.page.fields_dict.department.get_value(),
		};
	}

	async refresh() {
		await this.loadSummary();
		this.renderTree();
	}

	async loadSummary() {
		const response = await frappe.call({
			method: "hr_suite.hr_suite.api.get_employee_org_hierarchy_summary",
			args: this.getFilters(),
		});
		this.summary = response.message || {};
		this.scopeEl.text(this.summary.scope_label || __("Scoped view"));
		this.employeeCountEl.text(this.summary.employee_count ?? 0);
		this.departmentCountEl.text(this.summary.department_count ?? 0);
		this.managerCountEl.text(this.summary.manager_count ?? 0);
		this.approverCountEl.text(this.summary.approver_count ?? 0);
	}

	renderTree() {
		this.treeHost.empty();
		this.tree = new frappe.ui.Tree({
			parent: this.treeHost,
			label: this.summary?.root_label || __("Organization"),
			root_value: "__org_root__",
			expandable: true,
			with_skeleton: 0,
			args: this.getFilters(),
			method: "hr_suite.hr_suite.api.get_employee_org_tree_nodes",
			get_label: (node) => this.getNodeLabel(node),
			on_click: (node) => this.renderDetails(node),
		});
	}

	getNodeLabel(node) {
		const data = node.data || {};
		if (node.is_root) {
			return `<span class="employee-org-tree__node"><span class="employee-org-tree__badge employee-org-tree__badge--department">${__("Root")}</span><span class="employee-org-tree__node-title">${frappe.utils.escape_html(node.label)}</span></span>`;
		}

		if (data.node_type === "department") {
			return `
				<span class="employee-org-tree__node">
					<span class="employee-org-tree__badge employee-org-tree__badge--department">${__("Department")}</span>
					<span class="employee-org-tree__node-title">${frappe.utils.escape_html(data.department_label || data.title || node.label)}</span>
					<span class="employee-org-tree__node-meta">${__("Employees")}: ${data.employee_count || 0}</span>
				</span>
			`;
		}

		return `
			<span class="employee-org-tree__node">
				<span class="employee-org-tree__badge employee-org-tree__badge--employee">${__("Employee")}</span>
				<span class="employee-org-tree__node-title">${frappe.utils.escape_html(data.employee_name || data.title || node.label)}</span>
				<span class="employee-org-tree__node-meta">${frappe.utils.escape_html(data.designation || __("No designation"))}</span>
			</span>
		`;
	}

	renderDetails(node) {
		const data = node.data || {};
		if (node.is_root) {
			this.detailEl.html(`<div class="employee-org-tree__empty">${__("Root groups all scoped departments beneath the current filters.")}</div>`);
			return;
		}

		const rows = [];
		if (data.node_type === "department") {
			rows.push([__("Department"), data.department_label || __("Unassigned")]);
			rows.push([__("Employees"), data.employee_count || 0]);
			rows.push([__("Managers"), data.manager_count || 0]);
			rows.push([__("Approver references"), data.approver_count || 0]);
		} else {
			rows.push([__("Employee"), data.employee_name || data.employee || __("Unknown")]);
			rows.push([__("Employee ID"), data.employee || __("Not set")]);
			rows.push([__("Designation"), data.designation || __("Not set")]);
			rows.push([__("Department"), data.department_label || __("Not set")]);
			rows.push([__("Branch"), data.branch || __("Not set")]);
			rows.push([__("Company"), data.company || __("Not set")]);
			rows.push([__("Direct manager"), data.reports_to_name || data.reports_to || __("Not set")]);
			rows.push([__("Leave approver"), data.leave_approver || __("Not set")]);
			rows.push([__("Expense approver"), data.expense_approver || __("Not set")]);
			rows.push([__("User"), data.user_id || __("Not set")]);
			rows.push([__("Direct reports"), data.direct_report_count || 0]);
		}

		this.detailEl.html(`
			<div class="employee-org-tree__detail-grid">
				${rows
					.map(
						([label, value]) => `
							<div class="employee-org-tree__detail">
								<div class="employee-org-tree__detail-label">${frappe.utils.escape_html(String(label))}</div>
								<div class="employee-org-tree__detail-value">${frappe.utils.escape_html(String(value))}</div>
							</div>
						`
					)
					.join("")}
			</div>
		`);
	}

	expandAll() {
		if (this.tree?.root_node) {
			this.tree.load_children(this.tree.root_node, true);
		}
	}
};