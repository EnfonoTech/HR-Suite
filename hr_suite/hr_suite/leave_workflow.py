"""The Leave Application approval workflow, and a doctor for one that does not show its buttons.

The stock Leave Application has a Status field the approver edits, which gives no Approve or
Reject buttons. This ships one Workflow on that field (Open -> Approved or Rejected) so the
named Leave Approver sees both buttons, in the Workflow Action list too, and nobody can
approve their own leave. HRMS knows a Leave Application workflow exists and then leaves
self-approval to it, so the workflow is the single approval mechanism.

It never takes over from a workflow a client already runs: Frappe keeps one active workflow per
DocType and would silently switch theirs off, so this one is created inactive when another is
active, and `diagnose` says what is wrong with the active one.

Nothing here builds SQL from strings. Every f-string or .format() produces display text.
"""

import frappe
from frappe import _
from frappe.utils import cint

# No alert email on purpose: Frappe attaches the print as a PDF to it, and a PDF failure inside the
# Approve click would roll the approval back. Approvers are notified by HRMS (HR Settings > Leave
# Notification) and see the request in their Workflow Action list.

WORKFLOW = "Leave Application Approval"
DOCTYPE = "Leave Application"
STATE_FIELD = "status"

NOT_SELF = "frappe.session.user != frappe.db.get_value('Employee', doc.employee, 'user_id')"
IS_APPROVER = "frappe.session.user == doc.leave_approver and " + NOT_SELF


def _definition():
	def move(state, action, next_state, role, condition=""):
		return {
			"state": state,
			"action": action,
			"next_state": next_state,
			"allowed": role,
			"condition": condition,
			"allow_self_approval": 0,
		}

	return {
		"doctype": "Workflow",
		"workflow_name": WORKFLOW,
		"document_type": DOCTYPE,
		"module": "Hr Suite",
		"workflow_state_field": STATE_FIELD,
		"send_email_alert": 0,
		"override_status": 0,
		"states": [
			{"state": "Open", "doc_status": "0", "allow_edit": "Employee", "style": "Warning"},
			{"state": "Approved", "doc_status": "1", "allow_edit": "Leave Approver", "style": "Success"},
			{"state": "Rejected", "doc_status": "1", "allow_edit": "Leave Approver", "style": "Danger"},
			{"state": "Cancelled", "doc_status": "2", "allow_edit": "HR Manager", "style": "Danger"},
		],
		"transitions": [
			move("Open", "Approve", "Approved", "Leave Approver", IS_APPROVER),
			move("Open", "Approve", "Approved", "HR Manager", NOT_SELF),
			move("Open", "Reject", "Rejected", "Leave Approver", IS_APPROVER),
			move("Open", "Reject", "Rejected", "HR Manager", NOT_SELF),
			move("Approved", "Cancel", "Cancelled", "HR Manager"),
			move("Rejected", "Cancel", "Cancelled", "HR Manager"),
		],
	}


def ensure_workflow():
	"""Create or refresh the workflow. Called after every migrate; never changes is_active once it exists."""
	if not frappe.db.exists("DocType", DOCTYPE):
		return
	for state, style in (("Open", "Warning"), ("Approved", "Success"), ("Rejected", "Danger"), ("Cancelled", "Danger")):
		if not frappe.db.exists("Workflow State", state):
			frappe.get_doc({"doctype": "Workflow State", "workflow_state_name": state, "style": style}).insert(
				ignore_permissions=True
			)
	for action in ("Approve", "Reject", "Cancel"):
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": action}).insert(
				ignore_permissions=True
			)

	definition = _definition()
	try:
		if frappe.db.exists("Workflow", WORKFLOW):
			doc = frappe.get_doc("Workflow", WORKFLOW)
			keep_active = doc.is_active
			doc.update({k: v for k, v in definition.items() if k not in ("doctype",)})
			doc.is_active = keep_active
			doc.save(ignore_permissions=True)
			return
		other = frappe.db.get_value("Workflow", {"document_type": DOCTYPE, "is_active": 1, "name": ["!=", WORKFLOW]}, "name")
		doc = frappe.get_doc(definition)
		doc.is_active = 0 if other else 1
		doc.insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "HR Suite: Leave Application workflow sync failed")


@frappe.whitelist()
def diagnose(application=None, user=None):
	"""Why does `user` not see Approve / Reject on `application`? A list of findings, worst first.

	The checks are the ones a missing button comes down to: no active workflow, a state the
	workflow does not know, no transition out of it, the user's roles, a transition condition,
	read/write permission, User Permissions, and the self-approval rule.
	"""
	frappe.only_for(("HR Manager", "System Manager"))  # it reveals other users' roles
	if application:
		frappe.has_permission(DOCTYPE, "read", doc=application, throw=True)
	user = user or frappe.session.user
	findings = []

	name = frappe.db.get_value("Workflow", {"document_type": DOCTYPE, "is_active": 1}, "name")
	if not name:
		findings.append(_("No active Workflow on {0}: there are no Approve / Reject buttons. Activate '{1}'.").format(DOCTYPE, WORKFLOW))
		return findings
	workflow = frappe.get_doc("Workflow", name)
	findings.append(_("Active workflow: {0}, state field {1}.").format(name, workflow.workflow_state_field))

	if not application:
		return findings
	doc = frappe.get_doc(DOCTYPE, application)
	state = doc.get(workflow.workflow_state_field)
	if not state:
		findings.insert(0, _("{0} has no value in {1}, so no transition can match.").format(application, workflow.workflow_state_field))
		return findings
	known = {row.state for row in workflow.states}
	if state not in known:
		findings.insert(0, _("State '{0}' is not a state of {1}.").format(state, name))
		return findings

	roles = set(frappe.get_roles(user))
	from frappe.model.workflow import get_workflow_safe_globals

	out = [row for row in workflow.transitions if row.state == state]
	if not out:
		findings.insert(0, _("No transition leaves state '{0}'.").format(state))
	for row in out:
		label = "{0} ({1})".format(row.action, row.allowed)
		if row.allowed not in roles:
			findings.append(_("{0}: {1} does not hold the role {2}.").format(label, user, row.allowed))
			continue
		if row.condition:
			try:
				scope = get_workflow_safe_globals()
				scope["frappe"].session = frappe._dict(user=user)  # evaluate as that user, not as the caller
				ok = frappe.safe_eval(row.condition, scope, dict(doc=doc.as_dict()))
			except Exception as exc:
				findings.insert(0, _("{0}: the condition raised {1}.").format(label, exc))
				continue
			if not ok:
				findings.append(_("{0}: the condition is false for {1}: {2}").format(label, user, row.condition))
				continue
		if not cint(row.allow_self_approval) and user == doc.owner and user != "Administrator":
			findings.append(_("{0}: {1} created this document and the transition forbids self-approval.").format(label, user))
			continue
		findings.append(_("{0}: available to {1}.").format(label, user))

	for ptype in ("read", "write"):
		if not frappe.has_permission(DOCTYPE, ptype, doc=doc, user=user):
			findings.insert(0, _("{0} has no {1} permission on {2}: check role permissions and User Permissions.").format(user, ptype, application))
	if doc.leave_approver and doc.leave_approver != user:
		findings.append(_("The Leave Approver on this application is {0}, not {1}.").format(doc.leave_approver, user))
	return findings
