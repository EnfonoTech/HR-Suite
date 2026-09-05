// HR Suite — Payroll Preview list view

frappe.listview_settings["Payroll Preview"] = {
	add_fields: ["number_of_employees", "employees_with_issues", "last_refreshed_on"],

	get_indicator(doc) {
		if (!doc.last_refreshed_on) {
			return [__("Not Refreshed"), "gray", "last_refreshed_on,is,not set"];
		}

		if (cint(doc.employees_with_issues) > 0) {
			return [
				__("{0} with Issues", [cint(doc.employees_with_issues)]),
				"red",
				"employees_with_issues,>,0",
			];
		}

		return [__("Ready"), "green", "employees_with_issues,=,0"];
	},
};
