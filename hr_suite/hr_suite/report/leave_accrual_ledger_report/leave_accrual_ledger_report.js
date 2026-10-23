frappe.query_reports["Leave Accrual Ledger Report"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company" },
		{ fieldname: "employee", label: __("Employee"), fieldtype: "Link", options: "Employee" },
		{ fieldname: "source", label: __("Source"), fieldtype: "Select", options: "\nAccrual\nOpening\nAdjustment\nSettlement\nLeave Taken\nLeave Encashment" },
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date" },
	],
};
