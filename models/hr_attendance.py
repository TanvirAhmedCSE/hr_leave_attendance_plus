from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    scheduled_start = fields.Datetime(
        string="Scheduled Start", compute='_compute_late', store=True,
        help="Start of the employee's working schedule on the day of the check-in.",
    )
    late_minutes = fields.Integer(string="Late (min)", compute='_compute_late', store=True)
    is_late = fields.Boolean(string="Late", compute='_compute_late', store=True)

    @api.depends('check_in', 'employee_id')
    def _compute_late(self):
        """ Compare the first check-in of the day with the scheduled start of the employee. """
        rule_model = self.env['hr.attendance.rule']
        for attendance in self:
            attendance.scheduled_start = False
            attendance.late_minutes = 0
            attendance.is_late = False
            if not attendance.check_in or not attendance.employee_id:
                continue

            employee = attendance.employee_id.sudo()
            calendar = attendance.sudo()._get_employee_calendar()
            resource = employee.resource_id
            if not calendar or resource._is_flexible():
                continue  # No fixed schedule: lateness is meaningless.

            tz = pytz.timezone(calendar.tz or employee.tz or 'UTC')
            check_in_local = pytz.utc.localize(attendance.check_in).astimezone(tz)
            day_start = tz.localize(datetime.combine(check_in_local.date(), time.min))
            day_end = day_start + timedelta(days=1)
            intervals = calendar._work_intervals_batch(
                day_start, day_end, resources=resource
            )[resource.id]
            first_interval = next(iter(intervals), None)
            if not first_interval:
                continue  # Not a working day (weekend, public holiday, full-day time off).
            scheduled_start = first_interval[0]

            # Only the first check-in of the day can be late (ignore lunch-break check-ins).
            day_start_utc = day_start.astimezone(pytz.utc).replace(tzinfo=None)
            earlier_checkins = self.env['hr.attendance'].sudo().search_count([
                ('employee_id', '=', employee.id),
                ('check_in', '>=', day_start_utc),
                ('check_in', '<', attendance.check_in),
            ])
            attendance.scheduled_start = scheduled_start.astimezone(pytz.utc).replace(tzinfo=None)
            if earlier_checkins:
                continue

            rule = rule_model._get_rule(employee.company_id)
            delay = (check_in_local - scheduled_start).total_seconds() / 60.0
            if delay > rule.grace_minutes:
                attendance.late_minutes = int(delay)
                attendance.is_late = True
