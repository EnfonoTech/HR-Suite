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
			// Mark the ones an HR document raised on submit, so a human knows what to review.
			// employee_name is this doctype's title_field, and the subject column is written
			// with textContent — markup would show as literal angle brackets on every row,
			// and escaping it here would double-escape a name like "O'Brien & Sons".
			const name = value || "";
			return doc.auto_generated ? `${name} (${__("auto")})` : name;
		},
	},

	onload(listview) {
		listview.page.add_inner_button(__("Awaiting Payment"), () => {
			// clear() is async — it resets each standard filter through a promise chain —
			// so a filter added on the next line is blanked by the clear that follows it.
			listview.filter_area.clear().then(() => {
				listview.filter_area.add([["HR Payment Advice", "status", "=", "Approved"]]);
			});
		});
	},
};
