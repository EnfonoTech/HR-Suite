"""App-level invariants that a bench migrate or a print/notification run would otherwise
discover for the user.

Each check here corresponds to a defect that shipped: a Notification that Frappe refuses to
save, a status written on submit without allow_on_submit, a print format whose template does
not exist, and whitelisted endpoints that expose one employee's data to any logged-in user.
"""

import ast
import json
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase

APP_ROOT = Path(frappe.get_app_path("hr_suite"))
MODULE_ROOT = APP_ROOT / "hr_suite"

# Endpoints that legitimately take an `employee` argument without guarding it: they only
# return configuration for the caller's own country, never another employee's data.
UNGUARDED_BY_DESIGN = {"get_country_config_for_employee"}


class TestAppIntegrity(FrappeTestCase):
	def test_date_based_notifications_declare_a_date_field(self):
		"""Frappe throws "Please specify which date field must be checked" without it."""
		for path in (MODULE_ROOT / "notification").glob("*/*.json"):
			config = json.loads(path.read_text())
			if config.get("event") not in ("Days Before", "Days After"):
				continue
			fieldname = config.get("date_changed")
			self.assertTrue(fieldname, f"{config.get('name')}: no date_changed")

			doctype = config.get("document_type")
			if doctype and frappe.db.exists("DocType", doctype):
				self.assertTrue(
					frappe.get_meta(doctype).has_field(fieldname),
					f"{config.get('name')}: {doctype} has no field {fieldname}",
				)

	def test_fields_written_after_submit_allow_it(self):
		"""A submitted document cannot persist a field that lacks allow_on_submit."""
		post_submit = {"on_submit", "on_update_after_submit", "on_cancel", "before_cancel"}
		offenders = []

		for path in (MODULE_ROOT / "doctype").glob("*/*.py"):
			if path.stem.startswith("test_") or path.stem == "__init__":
				continue
			doctype = frappe.unscrub(path.stem)
			if not frappe.db.exists("DocType", doctype):
				continue
			meta = frappe.get_meta(doctype)
			if not meta.is_submittable:
				continue

			for node in ast.walk(ast.parse(path.read_text())):
				if not (isinstance(node, ast.FunctionDef) and node.name in post_submit):
					continue
				for inner in ast.walk(node):
					if not (isinstance(inner, ast.Assign) and len(inner.targets) == 1):
						continue
					target = inner.targets[0]
					if not (
						isinstance(target, ast.Attribute)
						and isinstance(target.value, ast.Name)
						and target.value.id == "self"
					):
						continue
					df = meta.get_field(target.attr)
					if df and not df.allow_on_submit:
						offenders.append(f"{doctype}.{target.attr} ({node.name})")

		self.assertEqual(offenders, [])

	def test_print_formats_have_a_template(self):
		"""A standard print format renders its .html file, else the html field — one must exist."""
		for path in (MODULE_ROOT / "print_format").glob("*/*.json"):
			config = json.loads(path.read_text())
			disk = path.parent / f"{path.parent.name}.html"
			has_template = disk.exists() or bool((config.get("html") or "").strip())
			self.assertTrue(has_template, f"{config.get('name')}: no template on disk or in html")

			if disk.exists():
				# a template split mid-expression renders nothing useful
				body = disk.read_text()
				self.assertEqual(body.count("{%"), body.count("%}"), config.get("name"))
				self.assertIn("</html>", body, config.get("name"))

	def test_employee_scoped_endpoints_are_guarded(self):
		"""Whitelisted endpoints taking an `employee` must check access to that employee."""
		guards = (
			"assert_employee_access",
			"has_permission",
			"check_permission",
			"only_for",
			"_require_employee_context",
			"assert_doctype_permissions",
		)
		unguarded = []

		for path in APP_ROOT.rglob("*.py"):
			if path.stem.startswith("test_"):
				continue
			for node in ast.walk(ast.parse(path.read_text())):
				if not isinstance(node, ast.FunctionDef):
					continue
				if not any("whitelist" in ast.unparse(d) for d in node.decorator_list):
					continue
				if node.name in UNGUARDED_BY_DESIGN:
					continue
				if "employee" not in [a.arg for a in node.args.args]:
					continue
				body = ast.unparse(node)
				if not any(guard in body for guard in guards):
					unguarded.append(f"{path.name}::{node.name}")

		self.assertEqual(unguarded, [])

	def test_no_whitelisted_endpoint_switches_user(self):
		"""frappe.set_user in a whitelisted method is privilege escalation."""
		offenders = []
		for path in APP_ROOT.rglob("*.py"):
			if path.stem.startswith("test_"):
				continue
			for node in ast.walk(ast.parse(path.read_text())):
				if not isinstance(node, ast.FunctionDef):
					continue
				if not any("whitelist" in ast.unparse(d) for d in node.decorator_list):
					continue
				if "frappe.set_user(" in ast.unparse(node):
					offenders.append(f"{path.name}::{node.name}")
		self.assertEqual(offenders, [])
