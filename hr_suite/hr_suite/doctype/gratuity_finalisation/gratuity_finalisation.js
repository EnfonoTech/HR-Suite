// HR Suite: Gratuity Finalisation. The review screen is the Gratuity Finalisation page; this form shows the result.
frappe.ui.form.on("Gratuity Finalisation", {
	refresh(frm) {
		if (frm.is_new()) {
			frm.set_intro(__("Use the Gratuity Finalisation page to review the figures and confirm."), "blue");
			frm.add_custom_button(__("Open Review Page"), () => frappe.set_route("gratuity-finalisation"));
		}
		frm.set_query("employee", () => ({ filters: { relieving_date: ["is", "set"] } }));
	},
});
