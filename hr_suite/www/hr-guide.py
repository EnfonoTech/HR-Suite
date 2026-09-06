import frappe
from frappe import _


def get_context(context):
	"""Serve the HR hand guide to signed-in staff only.

	The guide embeds screenshots of real employee records — names, salaries, loan
	balances and end-of-service figures. `www/` pages are public by default, so
	without this guard the whole HR data set would be readable by anyone with the
	URL. Guests are sent to the login screen and returned here afterwards.
	"""
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/hr-guide"
		raise frappe.Redirect

	context.no_cache = 1
	context.title = _("Steel Force HR — Hand Guide")
	return context
