frappe.ui.form.on("Leave Accrual Ledger", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.disable_form && frm.set_read_only();
		}
	},
});
