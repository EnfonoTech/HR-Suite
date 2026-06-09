// Copyright (c) 2026, Enfono and contributors
// For license information, please see license.txt

frappe.ui.form.on('HR Letter', {
	hr_letter_template: function(frm) {
		if (frm.doc.hr_letter_template) {
			frappe.db.get_value('HR Letter Template', frm.doc.hr_letter_template, 'terms', (r) => {
				if (r && r.terms) {
					frm.set_value('terms', r.terms);
				}
			});
		}
	},

	on_submit: function(frm) {
		frm.set_value('status', 'Issued');
	}
});
