frappe.query_reports["HR Payment Advice Queue"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company" },
		{ fieldname: "payment_type", label: __("Payment Type"), fieldtype: "Select",
		  options: "\nExpense Claim\nLeave Salary\nLeave Encashment\nGratuity\nTicket\nOther" },
		{ fieldname: "stage", label: __("Stage"), fieldtype: "Select", default: "Awaiting Payment",
		  options: "Awaiting Payment\nAwaiting Approval\nRejected\nAll Open" },
	],
};
