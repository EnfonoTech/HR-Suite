"""Phase 5 - sick leave split across pay tiers, on the Leave Application."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, flt

from hr_suite.hr_suite.sick_leave_tiers import (
	monthly_deductions,
	split_days,
	summarise,
	unpaid_equivalent,
)
from hr_suite.hr_suite.test_leave_accrual_ledger import COMPANY, LedgerTestBase

KSA = [{"tier_days": 30, "pay_percent": 100}, {"tier_days": 60, "pay_percent": 75}, {"tier_days": 30, "pay_percent": 0}]


def days(start, count, weight=1.0):
	return [(add_days(start, i), weight) for i in range(count)]


def pay(segments):
	return [(s["label"], s["weight"]) for s in segments]


class TestSplitter(FrappeTestCase):
	def test_inside_the_first_tier_is_full_pay(self):
		segments, consumed = split_days(KSA, 0, days("2026-02-01", 10))
		self.assertEqual({s["pay_percent"] for s in segments}, {100.0})
		self.assertEqual(consumed, 10)
		self.assertEqual(unpaid_equivalent(segments), 0)

	def test_crossing_into_the_second_tier(self):
		segments, _ = split_days(KSA, 20, days("2026-03-01", 20))  # year days 21-40
		rows = summarise(segments)
		self.assertEqual([(r["tier_label"], r["days"]) for r in rows], [("Full pay", 10), ("75% pay", 10)])
		self.assertEqual(unpaid_equivalent(segments), 2.5)

	def test_crossing_into_unpaid(self):
		segments, _ = split_days(KSA, 85, days("2026-06-01", 10))  # days 86-95: 5 at 75%, 5 unpaid
		self.assertEqual(unpaid_equivalent(segments), 6.25)

	def test_past_the_last_tier_is_unpaid_and_flagged(self):
		segments, _ = split_days(KSA, 118, days("2026-09-01", 5))  # 2 in the last tier, 3 beyond
		self.assertEqual({s["pay_percent"] for s in segments}, {0.0})
		self.assertEqual([s["label"] for s in segments][-1], "Beyond annual entitlement")
		self.assertEqual(unpaid_equivalent(segments), 5)

	def test_days_before_eligibility_are_unpaid_and_use_no_tier(self):
		segments, consumed = split_days(KSA, 0, days("2026-02-10", 5), eligible_from="2026-02-12")
		self.assertEqual([s["label"] for s in segments][:2], ["Before eligibility"] * 2)
		self.assertEqual(consumed, 3)  # only the paid days count against the tiers
		self.assertEqual(unpaid_equivalent(segments), 2)

	def test_a_half_day_can_straddle_a_tier_edge(self):
		segments, consumed = split_days(KSA, 29.75, [("2026-03-01", 0.5)])
		self.assertEqual([(s["weight"], s["pay_percent"]) for s in segments], [(0.25, 100.0), (0.25, 75.0)])
		self.assertEqual(consumed, 0.5)

	def test_monthly_deductions_land_in_the_month_the_reduced_days_fall(self):
		# 10 days at 75% starting 25 January: 7 in January (25-31), 3 in February
		segments, _ = split_days(KSA, 30, days("2026-01-25", 10))
		out = monthly_deductions(segments, 100)
		self.assertEqual({str(k): v[1] for k, v in out.items()}, {"2026-01-01": 175.0, "2026-02-01": 75.0})
		self.assertEqual(str(out[list(out)[0]][0]), "2026-01-25")


class SickTestBase(LedgerTestBase):
	def setUp(self):
		self.booked = []
		counter = iter(range(1, 200))

		def fake_book(doc, component, currency, payroll_date, amount):
			name = "AS-SICK-%s" % next(counter)
			self.booked.append({"name": name, "date": str(payroll_date), "amount": flt(amount, 3), "for": doc.name})
			return name

		for p in (
			patch("hr_suite.hr_suite.leave_payroll.prepare_component", return_value=("Sick Leave Deduction", "SAR")),
			patch("hr_suite.hr_suite.leave_payroll.book_deduction", side_effect=fake_book),
			patch("hr_suite.hr_suite.sick_leave_tiers._expense_account", return_value=""),
			patch("hr_suite.hr_suite.sick_leave_tiers._component", return_value="Sick Leave Deduction"),
		):
			p.start()
			self.addCleanup(p.stop)
		self.set_country("SA", sick_leave_auto_split=1)

	def set_country(self, code, **values):
		cfg = frappe.get_doc("Country Config", code)
		original = {field: cfg.get(field) for field in values}
		for field, value in values.items():
			cfg.set(field, value)
		cfg.save(ignore_permissions=True)

		def restore():
			again = frappe.get_doc("Country Config", code)
			for field, value in original.items():
				again.set(field, value)
			again.save(ignore_permissions=True)

		self.addCleanup(restore)

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		hl = frappe.get_doc(doctype="Holiday List", holiday_list_name="HRS Sick HL", from_date="2026-01-01", to_date="2026-12-31")
		hl.insert(ignore_permissions=True)
		frappe.db.set_value("Company", COMPANY, "default_holiday_list", hl.name)
		frappe.db.set_value("Leave Type", "Sick Leave", "max_leaves_allowed", 120)

	def staff(self, name, country="SA", joined="2020-01-01"):
		emp = self.employee(name, country, joined)
		frappe.db.set_value("Employee", emp, "ctc", 3000)  # a 100 a day on a 30-day month
		alloc = frappe.get_doc(
			doctype="Leave Allocation", employee=emp, leave_type="Sick Leave", from_date="2026-01-01",
			to_date="2026-12-31", new_leaves_allocated=120,
		)
		alloc.insert(ignore_permissions=True)
		alloc.submit()
		return emp

	def sick(self, emp, start, end, submit=True, certificate="cert.pdf"):
		la = frappe.get_doc(
			doctype="Leave Application", employee=emp, leave_type="Sick Leave", from_date=start, to_date=end,
			status="Approved", company=COMPANY, medical_certificate=certificate,
		)
		la.insert(ignore_permissions=True)
		if submit:
			la.submit()
		return la

	def split(self, la):
		return [
			(r.tier_label, flt(r.days, 2))
			for r in frappe.get_all("Leave Application Sick Tier", filters={"parent": la.name}, fields=["tier_label", "days"], order_by="idx")
		]


class TestOnTheApplication(SickTestBase):
	def test_a_draft_shows_the_split_before_it_is_submitted(self):
		emp = self.staff("Draft")
		la = self.sick(emp, "2026-02-01", "2026-03-12", submit=False)  # 40 days
		self.assertEqual([(r.tier_label, flt(r.days, 2)) for r in la.sick_tier_split], [("Full pay", 30), ("75% pay", 10)])
		self.assertEqual(la.sick_unpaid_equivalent, 2.5)
		self.assertEqual(self.booked, [])  # nothing is deducted until it is submitted

	def test_submit_splits_and_books_the_unpaid_share_in_the_right_month(self):
		emp = self.staff("Submit")
		la = self.sick(emp, "2026-02-01", "2026-03-12")
		self.assertEqual(self.split(la), [("Full pay", 30), ("75% pay", 10)])
		# the 10 reduced days are 3-12 March: 2.5 unpaid-equivalent days x 100
		self.assertEqual([(b["date"], b["amount"]) for b in self.booked], [("2026-03-03", 250)])

	def test_a_second_leave_continues_where_the_first_stopped(self):
		emp = self.staff("Second")
		self.sick(emp, "2026-02-01", "2026-03-12")
		second = self.sick(emp, "2026-04-01", "2026-04-20")  # year days 41-60, all at 75%
		self.assertEqual(self.split(second), [("75% pay", 20)])
		self.assertEqual(self.booked[-1]["amount"], 500)

	def test_an_earlier_leave_submitted_late_re_splits_the_later_one(self):
		emp = self.staff("Late")
		april = self.sick(emp, "2026-04-01", "2026-04-20")
		self.assertEqual(self.split(april), [("Full pay", 20)])
		self.assertEqual(self.booked, [])

		self.sick(emp, "2026-02-01", "2026-03-12")  # 40 days before it
		self.assertEqual(self.split(frappe.get_doc("Leave Application", april.name)), [("75% pay", 20)])
		self.assertIn(("2026-04-01", 500), [(b["date"], b["amount"]) for b in self.booked if b["for"] == april.name])

	def test_cancelling_an_earlier_leave_gives_the_later_one_its_tiers_back(self):
		emp = self.staff("Cancel")
		first = self.sick(emp, "2026-02-01", "2026-03-12")
		second = self.sick(emp, "2026-04-01", "2026-04-20")
		first.cancel()
		self.assertEqual(self.split(frappe.get_doc("Leave Application", second.name)), [("Full pay", 20)])
		self.assertEqual(frappe.db.get_value("Leave Application", second.name, "sick_deduction_rows"), "[]")

	def test_days_before_eligibility_are_unpaid(self):
		self.set_country("BH", sick_leave_auto_split=1)
		emp = self.staff("Early", country="BH", joined="2026-02-01")  # eligible from 1 May
		la = self.sick(emp, "2026-02-10", "2026-02-14")
		self.assertEqual(self.split(la), [("Before eligibility", 5)])
		self.assertEqual(self.booked[-1]["amount"], 500)

	def test_a_country_not_switched_over_is_left_alone(self):
		self.set_country("SA", sick_leave_auto_split=0)
		emp = self.staff("Off")
		la = self.sick(emp, "2026-02-01", "2026-03-12")
		self.assertEqual(self.split(la), [])
		self.assertEqual(self.booked, [])

	def test_annual_leave_is_not_touched(self):
		emp = self.staff("Annual")
		la = frappe.get_doc(
			doctype="Leave Application", employee=emp, leave_type="Annual Leave", from_date="2026-02-01",
			to_date="2026-02-05", status="Approved", company=COMPANY,
		)
		with patch("hr_suite.hr_suite.leave_accrual.check_annual_leave_rules"):
			la.insert(ignore_permissions=True)
		self.assertEqual(la.get("sick_tier_split") or [], [])


class TestCertificate(SickTestBase):
	def test_a_certificate_is_required_to_submit(self):
		emp = self.staff("NoCert")
		la = self.sick(emp, "2026-02-01", "2026-02-03", submit=False, certificate=None)
		with patch("frappe.get_roles", return_value=["Employee"]):
			self.assertRaises(frappe.ValidationError, la.submit)

	def test_hr_with_the_override_role_may_submit_without_one(self):
		emp = self.staff("HrCert")
		la = self.sick(emp, "2026-02-01", "2026-02-03", submit=False, certificate=None)
		with patch("frappe.get_roles", return_value=["HR Leave Override"]):
			la.submit()
		self.assertEqual(la.docstatus, 1)

	def test_an_attached_certificate_passes(self):
		emp = self.staff("WithCert")
		self.assertEqual(self.sick(emp, "2026-02-01", "2026-02-03").docstatus, 1)


class TestLegacySickLeaveDocument(SickTestBase):
	def setUp(self):
		super().setUp()
		# Saving a Sick Leave starts its approval workflow, which emails a PDF (needs wkhtmltopdf).
		stub = patch("frappe.workflow.doctype.workflow_action.workflow_action.send_workflow_action_email")
		stub.start()
		self.addCleanup(stub.stop)

	def legacy(self, emp, start, end):
		return frappe.get_doc(doctype="Sick Leave", employee=emp, company=COMPANY, from_date=start, to_date=end)

	def test_a_new_one_is_refused_where_the_split_is_on(self):
		emp = self.staff("Refused")
		self.assertRaises(frappe.ValidationError, self.legacy(emp, "2026-02-01", "2026-02-05").insert, ignore_permissions=True)

	def test_it_prices_from_the_country_tiers_where_the_split_is_off(self):
		self.set_country("SA", sick_leave_auto_split=0)
		emp = self.staff("Legacy")
		doc = self.legacy(emp, "2026-02-01", "2026-03-12")  # 40 days: 30 full + 10 at 75%
		doc.insert(ignore_permissions=True)
		self.assertEqual(doc.total_days, 40)
		self.assertEqual(doc.leave_pay_amount, 3750)  # (30 + 7.5) x 100

	def test_the_yearly_limit_is_the_countrys_not_saudi_arabias(self):
		self.set_country("SA", sick_leave_auto_split=0)
		emp = self.staff("Limit")
		self.assertRaises(frappe.ValidationError, self.legacy(emp, "2026-01-01", "2026-05-02").insert, ignore_permissions=True)  # 122 days
