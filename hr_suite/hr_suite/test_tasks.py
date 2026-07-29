from unittest.mock import patch

from frappe.tests.utils import FrappeTestCase

from hr_suite.hr_suite import tasks as tasks_module


class TestSaudiHRTasks(FrappeTestCase):
	def test_should_send_days_left_alert_only_for_milestones(self):
		self.assertTrue(tasks_module._should_send_days_left_alert(60, 60))
		self.assertTrue(tasks_module._should_send_days_left_alert(30, 60))
		self.assertTrue(tasks_module._should_send_days_left_alert(7, 60))
		self.assertFalse(tasks_module._should_send_days_left_alert(59, 60))
		self.assertFalse(tasks_module._should_send_days_left_alert(5, 60))

	def test_get_pending_alert_recipients_skips_existing_notifications(self):
		with patch.object(tasks_module, "_has_existing_alert", side_effect=lambda user, *_args: user == "hr@example.com"):
			recipients = tasks_module._get_pending_alert_recipients(
				["hr@example.com", "manager@example.com"],
				"Contract alert",
				"Country Employment Contract",
				"CONT-0001",
			)

		self.assertEqual(recipients, ["manager@example.com"])