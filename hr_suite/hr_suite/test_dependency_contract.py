from pathlib import Path

from frappe.tests.utils import FrappeTestCase

from hr_suite import hooks
from hr_suite.hr_suite.utils import is_saudi_nationality


APP_ROOT = Path(__file__).resolve().parents[2]


class TestDependencyContract(FrappeTestCase):
	def test_required_apps_do_not_pull_hrms(self):
		required_apps = {_normalize_app_name(app) for app in hooks.required_apps}

		self.assertIn("erpnext", required_apps)
		self.assertNotIn("hrms", required_apps)

	def test_base_dependencies_are_declared_in_all_install_files(self):
		for relative_path in ("setup.py", "pyproject.toml", "requirements.txt"):
			text = (APP_ROOT / relative_path).read_text()
			self.assertIn("openpyxl>=3.1.0", text)
			self.assertIn("openlocationcode>=1.0.1", text)

	def test_voice_dependencies_are_optional_and_documented(self):
		setup_text = (APP_ROOT / "setup.py").read_text()
		pyproject_text = (APP_ROOT / "pyproject.toml").read_text()
		voice_requirements = (APP_ROOT / "requirements-voice-cpu.txt").read_text()

		for text in (setup_text, pyproject_text):
			self.assertIn("voice-full", text)
			self.assertIn("speechbrain", text)
			self.assertIn("faster-whisper", text)

		self.assertIn("torch==2.2.2", voice_requirements)
		self.assertIn("torchaudio==2.2.2", voice_requirements)
		self.assertIn("speechbrain>=1.1.0", voice_requirements)
		self.assertIn("faster-whisper>=1.2.1", voice_requirements)

	def test_hr_suite_doctypes_do_not_fetch_optional_employee_identity_fields(self):
		doctype_root = APP_ROOT / "hr_suite" / "hr_suite" / "doctype"
		for path in doctype_root.glob("*/*.json"):
			text = path.read_text()
			self.assertNotIn("employee.nationality", text, path)
			self.assertNotIn("employee.iqama_number", text, path)
			self.assertNotIn("employee.passport_number", text, path)

	def test_bilingual_saudi_nationality_is_recognized(self):
		self.assertTrue(is_saudi_nationality("Saudi"))
		self.assertTrue(is_saudi_nationality("saudi arabia"))
		self.assertFalse(is_saudi_nationality("Jordanian"))


def _normalize_app_name(required_app):
	return str(required_app).split("/")[-1]
