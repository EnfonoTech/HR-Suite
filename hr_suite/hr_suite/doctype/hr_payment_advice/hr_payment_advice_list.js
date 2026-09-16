// Copyright (c) 2026, Hr Suite and contributors
// HR Payment Advice list: colour by status, and surface what finance still owes someone.

frappe.listview_settings["HR Payment Advice"] = {
	add_fields: ["status", "total_amount", "employee_name", "payment_date", "auto_generated"],

	get_indicator(doc) {
		const map = {
			Draft: ["Draft", "gray", "status,=,Draft"],
			"Pending Approval": ["Pending Approval", "orange", "status,=,Pending Approval"],
			Approved: ["Awaiting Payment", "blue", "status,=,Approved"],
			Paid: ["Paid", "green", "status,=,Paid"],
			Cancelled: ["Cancelled", "red", "status,=,Cancelled"],
		};
		return map[doc.status] || [doc.status, "gray", "status,=," + doc.status];
	},

	formatters: {
		employee_name(value, df, doc) {
			// mark the ones an HR document raised on submit, so a human knows what to review
			const name = frappe.utils.escape_html(value || "");
			return doc.auto_generated
				? `${name} <span class="indicator-pill gray" title="${__("Raised by an HR document")}">${__("auto")}</span>`
				: name;
		},
	},

	onload(listview) {
		listview.page.add_inner_button(__("Awaiting Payment"), () => {
			listview.filter_area.clear();
			listview.filter_area.add([["HR Payment Advice", "status", "=", "Approved"]]);
		});
	},
};
