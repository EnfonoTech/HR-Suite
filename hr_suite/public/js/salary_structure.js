// HR Suite — Salary Structure: take the currency from the company, not from the user's default.
// A user whose default currency is another country's would otherwise get that one on this company's structure.
frappe.ui.form.on("Salary Structure", {
	company: function (frm) {
		hr_suite_set_structure_currency(frm);
	},

	onload: function (frm) {
		if (frm.is_new() && frm.doc.company) hr_suite_set_structure_currency(frm);
	},
});

function hr_suite_set_structure_currency(frm) {
	if (!frm.doc.company || frm.doc.docstatus !== 0) return;
	frappe.db.get_value("Company", frm.doc.company, "default_currency").then((r) => {
		const currency = r && r.message && r.message.default_currency;
		if (currency && frm.doc.currency !== currency) frm.set_value("currency", currency);
	});
}
