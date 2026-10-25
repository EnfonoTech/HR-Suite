// Copyright (c) 2026, Hr Suite and contributors
// HR Payment Advice — HR raises it, finance confirms the payment here.

const FLOW = "hr_suite.hr_suite.payment_advice_flow";

function flow_call(frm, method, args, message) {
	frappe.call({
		method: FLOW + "." + method,
		args: Object.assign({ name: frm.doc.name }, args || {}),
		freeze: true,
		freeze_message: message,
		callback() {
			frm.reload_doc();
		},
	});
}

frappe.ui.form.on("HR Payment Advice", {
	setup(frm) {
		frm.set_query("approver_l1", () => ({ filters: { enabled: 1, user_type: "System User" } }));
		frm.set_query("approver_l2", () => ({ filters: { enabled: 1, user_type: "System User" } }));
	},

	// A new row sanctions what it claims until HR says otherwise.
	references_add(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.sanctioned_amount == null) frappe.model.set_value(cdt, cdn, "sanctioned_amount", row.amount || 0);
	},

	refresh(frm) {
		const status = frm.doc.status;

		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			if (["Draft", "Rejected"].includes(status)) {
				frm.add_custom_button(__("Send for Approval"), () => flow_call(frm, "submit_for_approval", {}, __("Sending...")))
					.addClass("btn-primary");
			}
			if (status === "Pending Approval") {
				frm.dashboard.set_headline(
					__("Waiting for the level {0} approver", [frm.doc.approval_level || 1]), "orange"
				);
				const me = frappe.session.user;
				const mine = (frm.doc.approval_level === 2 ? frm.doc.approver_l2 : frm.doc.approver_l1) === me;
				if (mine) {
					frm.add_custom_button(__("Approve"), () => flow_call(frm, "approve", {}, __("Approving...")))
						.addClass("btn-primary");
					frm.add_custom_button(__("Reject"), () => {
						frappe.prompt(
							[{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 }],
							(v) => flow_call(frm, "reject", { reason: v.reason }, __("Rejecting...")),
							__("Reject Payment Advice"),
							__("Reject")
						);
					});
				}
				frm.add_custom_button(__("Recall"), () => flow_call(frm, "recall", {}, __("Recalling...")));
			}
			if (status === "Rejected") {
				frm.dashboard.set_headline(
					__("Rejected: {0}", [frappe.utils.escape_html(frm.doc.rejection_reason || "")]), "red"
				);
			}
		}

		if (frm.doc.docstatus === 1 && status === "Approved") {
			frm.add_custom_button(__("Send to Finance"), () => flow_call(frm, "send_to_finance", {}, __("Sending...")));
		}

		// Only a submitted advice that has not been paid can be confirmed. A draft is
		// still HR's, and a paid one already has a reference that must not be rewritten.
		const leave_salary = frm.doc.source_doctype === "Leave Salary Settlement"
			|| (frm.doc.references || []).some((r) => r.reference_doctype === "Leave Salary Settlement");
		if (frm.doc.docstatus === 1 && !["Paid", "Cancelled"].includes(status)) {
			if (leave_salary) {
				// Leave salary is paid with a Payment Entry against the employee's payable, never marked paid by hand.
				if (["Approved", "Sent to Finance", "Partially Paid"].includes(status) && frappe.model.can_create("Payment Entry")) {
					frm.add_custom_button(__("Create Payment Entry"), function () {
						frappe.call({
							method: "hr_suite.hr_suite.payment_advice.make_payment_entry",
							args: { advice: frm.doc.name },
							freeze: true,
							callback: function (r) {
								if (r.message && r.message.payment_entry) {
									frappe.set_route("Form", "Payment Entry", r.message.payment_entry);
								}
							},
						});
					}).addClass("btn-primary");
				}
			} else {
				frm.add_custom_button(__("Mark as Paid"), () => mark_paid_dialog(frm)).addClass("btn-primary");
			}
		}

		if (frm.doc.docstatus === 1 && status === "Partially Paid") {
			frm.dashboard.set_headline(
				__("Partly paid: {0} of {1}. Create another Payment Entry for the balance.", [
					format_currency(frm.doc.amount_paid, frm.doc.currency), format_currency(frm.doc.total_amount, frm.doc.currency),
				]),
				"orange"
			);
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
