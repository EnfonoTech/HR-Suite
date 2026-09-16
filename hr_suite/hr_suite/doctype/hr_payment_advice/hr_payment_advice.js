// Copyright (c) 2026, Hr Suite and contributors
// HR Payment Advice — HR raises it, finance confirms the payment here.

frappe.ui.form.on("HR Payment Advice", {
	refresh(frm) {
		// Only a submitted advice that has not been paid can be confirmed. A draft is
		// still HR's, and a paid one already has a reference that must not be rewritten.
		if (frm.doc.docstatus === 1 && frm.doc.status !== "Paid") {
			frm.add_custom_button(__("Mark as Paid"), () => mark_paid_dialog(frm)).addClass("btn-primary");
		}

		if (frm.doc.docstatus === 1 && frm.doc.status === "Paid") {
			frm.dashboard.set_headline(
				__("Paid on {0} — reference {1}", [
					frappe.datetime.str_to_user(frm.doc.payment_date),
					frappe.utils.escape_html(frm.doc.payment_reference || "—"),
				])
			);
		}

		if (frm.doc.source_doctype && frm.doc.source_name) {
			frm.add_custom_button(
				__("{0} {1}", [__(frm.doc.source_doctype), frm.doc.source_name]),
				() => frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name),
				__("View")
			);
		}
	},
});

function mark_paid_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Confirm Payment"),
		fields: [
			{
				fieldname: "payment_reference",
				fieldtype: "Data",
				label: __("Payment Reference"),
				reqd: 1,
				description: __("Cheque number, transfer reference or WPS batch."),
			},
			{
				fieldname: "payment_date",
				fieldtype: "Date",
				label: __("Payment Date"),
				reqd: 1,
				default: frappe.datetime.get_today(),
			},
			{
				fieldname: "bank_account",
				fieldtype: "Link",
				label: __("Bank Account"),
				options: "Bank Account",
				default: frm.doc.bank_account,
			},
		],
		primary_action_label: __("Mark as Paid"),
		primary_action(values) {
			dialog.hide();
			frappe.call({
				method: "hr_suite.hr_suite.payment_advice.mark_paid",
				args: {
					advice: frm.doc.name,
					payment_reference: values.payment_reference,
					payment_date: values.payment_date,
					bank_account: values.bank_account,
				},
				freeze: true,
				freeze_message: __("Confirming payment..."),
				callback(r) {
					if (!r.message) return;
					if (r.message.already_paid) {
						frappe.show_alert({ message: __("This advice was already paid."), indicator: "orange" });
					}
					frm.reload_doc();
				},
			});
		},
	});

	dialog.show();
}
