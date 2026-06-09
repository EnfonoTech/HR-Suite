frappe.ui.form.on("Staff Rating", {
	refresh(frm) {
		if (frm.doc.rated_by_employee) {
			frm.set_df_property("rated_by_employee", "hidden", 0);
		}
	},
});
