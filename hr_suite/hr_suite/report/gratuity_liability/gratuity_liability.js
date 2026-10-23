frappe.query_reports["Gratuity Liability"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company" },
		{ fieldname: "department", label: __("Department"), fieldtype: "Link", options: "Department" },
		{ fieldname: "as_on", label: __("As On"), fieldtype: "Date", default: frappe.datetime.get_today() },
	],
};
