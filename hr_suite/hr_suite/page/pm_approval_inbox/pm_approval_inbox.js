// PM Approval Inbox — standalone page accessible to all logged-in users
// Author: siva <siva@enfono.com>

frappe.pages["pm-approval-inbox"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("My Approvals"),
		single_column: true,
	});

	wrapper.page = page;

	// The bundle (loaded globally) exports window.pm_approval_inbox
	const inbox = new window.pm_approval_inbox.ApprovalInbox({
		wrapper: $(page.body),
	});

	wrapper.approval_inbox = inbox;
};

frappe.pages["pm-approval-inbox"].on_page_show = function (wrapper) {
	// Reload every time the user navigates back to the page
	if (wrapper.approval_inbox) {
		wrapper.approval_inbox.load();
	}
};
