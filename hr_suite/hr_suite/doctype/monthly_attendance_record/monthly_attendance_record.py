import frappe
from frappe.model.document import Document
from frappe import _
import calendar


MONTH_MAP = {
    "January": 1, "February": 2, "March": 3,
    "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9,
    "October": 10, "November": 11, "December": 12
}

DAYS_AR = {
    0: "Monday", 1: "Tuesday", 2: "Wednesday",
    3: "Thursday", 4: "Friday", 5: "Saturday",
    6: "Sunday"
}


class MonthlyAttendanceRecord(Document):
    def validate(self):
        self._recalculate_summary()

    def _recalculate_summary(self):
        """Compute summary fields from child attendance_details rows."""
        if not self.attendance_details:
            return

        totals = {
            "total_working_days": 0,
            "actual_present_days": 0,
            "absent_days": 0,
            "late_days": 0,
            "late_minutes_total": 0,
            "overtime_hours_total": 0.0,
            "annual_leave_days": 0,
            "sick_leave_days": 0,
            "maternity_leave_days": 0,
            "special_leave_days": 0,
            "unpaid_leave_days": 0,
            "other_leave_days": 0,
        }

        for row in self.attendance_details:
            # Set day_of_week from date
            if row.attendance_date:
                import datetime
                d = row.attendance_date if isinstance(row.attendance_date, datetime.date) else \
                    datetime.date.fromisoformat(str(row.attendance_date))
                row.day_of_week = DAYS_AR.get(d.weekday(), "")

            day_type = row.day_type or ""
            status = row.status or ""

            if "Working Day" in day_type:
                totals["total_working_days"] += 1

            if "Present" in status:
                totals["actual_present_days"] += 1
            elif "Absent" in status:
                totals["absent_days"] += 1
            elif "Late" in status:
                totals["actual_present_days"] += 1
                totals["late_days"] += 1

            totals["late_minutes_total"] += int(row.late_minutes or 0)
            totals["overtime_hours_total"] += float(row.overtime_hours or 0)

            if "Annual Leave" in day_type:
                totals["annual_leave_days"] += 1
            elif "Sick Leave" in day_type:
                totals["sick_leave_days"] += 1
            elif "Maternity Leave" in day_type:
                totals["maternity_leave_days"] += 1
            elif "Special Leave" in day_type:
                totals["special_leave_days"] += 1
            elif "Unpaid Leave" in day_type:
                totals["unpaid_leave_days"] += 1

        for field, val in totals.items():
            self.set(field, val)


@frappe.whitelist()
def get_monthly_days(month_label, year):
    """Return a list of days for the given month/year to pre-populate child table."""
    import datetime

    month_num = MONTH_MAP.get(month_label)
    if not month_num or not year:
        return []

    year = int(year)
    _, num_days = calendar.monthrange(year, month_num)
    rows = []
    for day in range(1, num_days + 1):
        d = datetime.date(year, month_num, day)
        weekday = d.weekday()
        if weekday == 4:  # Friday
            day_type = "Friday"
            status = "Holiday"
        elif weekday == 5:  # Saturday
            day_type = "Saturday"
            status = "Holiday"
        else:
            day_type = "Working Day"
            status = "Present"
        rows.append({
            "attendance_date": str(d),
            "day_of_week": DAYS_AR.get(weekday, ""),
            "day_type": day_type,
            "status": status,
        })
    return rows
