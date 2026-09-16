"""Switch off the retired monthly leave-allocation job, once, on every site.

``hr_suite.hr_suite.tasks.allocate_monthly_leave`` used to create one Leave
Allocation per employee per leave type per CALENDAR MONTH. Days allocated inside
a one-month window die with the window: on the 1st of the next month the balance
is gone, so nothing could ever be carried into the next year and a December
application could not spend a day earned in March. It also granted beside
whatever a Leave Policy Assignment had already granted — the same year of leave
issued twice.

Monthly accrual is HRMS's own earned-leave engine now (``Leave Type``
``is_earned_leave`` + ``earned_leave_frequency``, topped up on ONE year-long
allocation by hrms's daily scheduler), switched on per leave type from Country
Config. The job is retired and the setting that drove it is read-only, but a site
where it was ticked would keep reporting a monthly grant that no longer happens —
so it is cleared here, in the one place a site is touched exactly once.

The month-window allocations the old job created are deliberately NOT cancelled.
Each one expires at the end of its own month, and a cancellation would rewrite
Leave Ledger history for days employees may already have taken. They are reported
instead, by ``leave_setup.check_double_allocation_risk``, which runs on every
migrate.
"""

import frappe
from frappe.utils import cint


def execute():
	if not frappe.db.exists("DocType", "Hr Suite Settings"):
		return

	if not cint(frappe.db.get_single_value("Hr Suite Settings", "monthly_leave_allocation_enabled")):
		return

	frappe.db.set_single_value("Hr Suite Settings", "monthly_leave_allocation_enabled", 0)
	frappe.logger().info(
		"HR Suite: cleared the retired monthly_leave_allocation_enabled setting; leave now "
		"accrues through HRMS earned leave."
	)
