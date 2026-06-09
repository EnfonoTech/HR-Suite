const EMPLOYEE_LOAN_SECTION_DESCRIPTIONS = {
	loan_section: "Capture the approved loan amount, grant date, and disbursement accounting reference.",
	summary_section: "Track recovered amounts, remaining balance, and the installment schedule generated from the repayment method.",
};


frappe.ui.form.on("Employee Loan", {
	refresh(frm) {
		apply_employee_loan_section_descriptions(frm, EMPLOYEE_LOAN_SECTION_DESCRIPTIONS);
		apply_employee_loan_ui(frm);
	},

	repayment_method(frm) {
		set_loan_field_requirements(frm);
	},
});


function apply_employee_loan_ui(frm) {
	set_loan_field_requirements(frm);
	frm.clear_custom_buttons();
	const is_approver = frappe.user.has_role("HR Manager") || frappe.user.has_role("System Manager");

	if (frm.doc.docstatus === 0) {
		frm.add_custom_button(__("Generate Schedule"), async function () {
			await frm.save();
			frappe.show_alert({ message: __("Installment schedule refreshed"), indicator: "green" });
		});
	}

	if (frm.doc.docstatus === 0 && frm.doc.approval_status === "Draft") {
		frm.add_custom_button(__("Request Approval"), async function () {
			await frappe.call({
				method: "hr_suite.hr_suite.doctype.employee_loan.employee_loan.request_loan_approval",
				args: { doc_name: frm.doc.name },
			});
			await frm.reload_doc();
		});
	}

	if (frm.doc.docstatus === 0 && is_approver && frm.doc.approval_status === "Pending Approval") {
		frm.add_custom_button(__("Approve Loan"), async function () {
			await frappe.call({
				method: "hr_suite.hr_suite.doctype.employee_loan.employee_loan.approve_loan",
				args: { doc_name: frm.doc.name },
			});
			await frm.reload_doc();
		}, __("Approvals"));

		frm.add_custom_button(__("Reject Loan"), async function () {
			await frappe.call({
				method: "hr_suite.hr_suite.doctype.employee_loan.employee_loan.reject_loan",
				args: { doc_name: frm.doc.name },
			});
			await frm.reload_doc();
		}, __("Approvals"));
	}

	if (frm.doc.docstatus === 1 && is_approver && frm.doc.approval_status === "Approved" && !frm.doc.disbursement_journal_entry) {
		frm.add_custom_button(__("Approve Disbursement"), async function () {
			await frappe.call({
				method: "hr_suite.hr_suite.doctype.employee_loan.employee_loan.approve_loan_disbursement",
				args: { doc_name: frm.doc.name },
			});
			await frm.reload_doc();
		}, __("Approvals"));
	}

	if (frm.doc.docstatus === 1 && frm.doc.approval_status === "Ready for Disbursement" && !frm.doc.disbursement_journal_entry) {
		frm.add_custom_button(__("Create Disbursement Entry"), async function () {
			const response = await frappe.call({
				method: "hr_suite.hr_suite.doctype.employee_loan.employee_loan.create_disbursement_journal_entry",
				args: { doc_name: frm.doc.name },
			});
			await frm.reload_doc();
			if (response.message?.journal_entry) {
				frappe.set_route("Form", "Journal Entry", response.message.journal_entry);
			}
		});
	}

	if (frm.doc.disbursement_journal_entry) {
		frm.add_custom_button(__("View Disbursement Entry"), function () {
			frappe.set_route("Form", "Journal Entry", frm.doc.disbursement_journal_entry);
		});
	}

	if (frm.doc.installments?.length) {
		const pending = (frm.doc.installments || []).filter((row) => row.deduction_status === "Pending").length;
		const deducted = (frm.doc.installments || []).filter((row) => row.deduction_status === "Deducted").length;
		frm.dashboard.add_indicator(__('{0} deducted / {1} pending', [deducted, pending]), pending ? 'orange' : 'green');
	}

	if (frm.doc.repayment_method === "Equal Installments" && frm.doc.installment_count && frm.doc.loan_amount) {
		const monthly = (flt(frm.doc.loan_amount) / cint(frm.doc.installment_count)).toFixed(2);
		frm.dashboard.add_comment(__("Estimated installment: {0}", [format_currency(monthly)]), "blue", true);
	}
	if (frm.doc.repayment_method === "Fixed Installment Amount" && frm.doc.monthly_installment_amount) {
		frm.dashboard.add_comment(__("Fixed monthly installment: {0}", [format_currency(frm.doc.monthly_installment_amount)]), "blue", true);
	}
	if (frm.doc.approval_status) {
		frm.dashboard.add_comment(__("Approval Status: {0}", [frm.doc.approval_status]), "orange", true);
	}
}


function set_loan_field_requirements(frm) {
	const is_equal = frm.doc.repayment_method === "Equal Installments";
	frm.toggle_reqd("installment_count", is_equal);
	frm.toggle_reqd("monthly_installment_amount", !is_equal);
	frm.toggle_display("installment_count", is_equal);
	frm.toggle_display("monthly_installment_amount", !is_equal);
}


function apply_employee_loan_section_descriptions(frm, descriptions) {
	for (const [fieldname, description] of Object.entries(descriptions)) {
		frm.set_df_property(fieldname, "description", __(description));
	}
	frm.refresh_fields(Object.keys(descriptions));
}