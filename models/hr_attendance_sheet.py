import calendar as pycalendar
from datetime import date, datetime, time, timedelta

import pytz
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models, Command
from odoo.exceptions import UserError

MONTHS = [
    ('1', "January"), ('2', "February"), ('3', "March"), ('4', "April"),
    ('5', "May"), ('6', "June"), ('7', "July"), ('8', "August"),
    ('9', "September"), ('10', "October"), ('11', "November"), ('12', "December"),
]


class HrAttendanceSheet(models.Model):
    """ Monthly attendance and salary-deduction sheet (Odoo Community has no Payroll). """
    _name = 'hr.attendance.sheet'
    _description = 'Monthly Attendance & Deduction Sheet'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'year desc, month desc, id desc'

    name = fields.Char(compute='_compute_period', store=True)
    month = fields.Selection(
        MONTHS, required=True, default=lambda self: str(fields.Date.context_today(self).month),
        tracking=True,
    )
    year = fields.Integer(
        required=True, default=lambda self: fields.Date.context_today(self).year, tracking=True
    )
    date_from = fields.Date(compute='_compute_period', store=True)
    date_to = fields.Date(compute='_compute_period', store=True)
    company_id = fields.Many2one(
        'res.company', string="Company", required=True, default=lambda self: self.env.company
    )
    department_ids = fields.Many2many(
        'hr.department', string="Departments",
        help="Leave empty to include every employee of the company.",
    )
    state = fields.Selection([
        ('draft', "Draft"),
        ('confirmed', "Confirmed"),
        ('done', "Done"),
        ('cancelled', "Cancelled"),
    ], default='draft', required=True, tracking=True, copy=False)
    line_ids = fields.One2many('hr.attendance.sheet.line', 'sheet_id', string="Lines", copy=False)

    total_deduction_amount = fields.Float(compute='_compute_totals', store=True)
    total_ot_amount = fields.Float(compute='_compute_totals', store=True)
    total_net_adjustment = fields.Float(compute='_compute_totals', store=True)

    _period_uniq = models.Constraint(
        'unique(company_id, year, month)',
        "There is already a sheet for this month and company.",
    )

    #  COMPUTE METHODS  #

    @api.depends('month', 'year')
    def _compute_period(self):
        month_names = dict(MONTHS)
        for sheet in self:
            if sheet.month and sheet.year:
                month = int(sheet.month)
                last_day = pycalendar.monthrange(sheet.year, month)[1]
                sheet.date_from = date(sheet.year, month, 1)
                sheet.date_to = date(sheet.year, month, last_day)
                sheet.name = f"{month_names[sheet.month]} {sheet.year}"
            else:
                sheet.date_from = sheet.date_to = False
                sheet.name = False

    @api.depends('line_ids.deduction_amount', 'line_ids.ot_amount', 'line_ids.net_adjustment')
    def _compute_totals(self):
        for sheet in self:
            sheet.total_deduction_amount = sum(sheet.line_ids.mapped('deduction_amount'))
            sheet.total_ot_amount = sum(sheet.line_ids.mapped('ot_amount'))
            sheet.total_net_adjustment = sum(sheet.line_ids.mapped('net_adjustment'))

    #  ACTIONS  #

    def action_generate_lines(self):
        """ Add a line for each missing employee, then compute the figures of every line. """
        for sheet in self:
            if sheet.state != 'draft':
                raise UserError(_("Lines can only be generated on a draft sheet."))
            domain = [('company_id', '=', sheet.company_id.id)]
            if sheet.department_ids:
                domain.append(('department_id', 'in', sheet.department_ids.ids))
            employees = self.env['hr.employee'].search(domain)
            missing = employees - sheet.line_ids.employee_id
            sheet.write({
                'line_ids': [Command.create({'employee_id': emp.id}) for emp in missing],
            })
            sheet.line_ids._refresh_figures()

    def action_refresh_figures(self):
        for sheet in self:
            if sheet.state != 'draft':
                raise UserError(_("Figures can only be refreshed on a draft sheet."))
            sheet.line_ids._refresh_figures()

    def action_confirm(self):
        for sheet in self:
            if sheet.state != 'draft':
                raise UserError(_("Only draft sheets can be confirmed."))
            if not sheet.line_ids:
                raise UserError(_("Generate the lines before confirming the sheet."))
        self.write({'state': 'confirmed'})

    def action_done(self):
        for sheet in self:
            if sheet.state != 'confirmed':
                raise UserError(_("Only confirmed sheets can be marked as done."))
        self.write({'state': 'done'})

    def action_cancel(self):
        for sheet in self:
            if sheet.state == 'done':
                raise UserError(_("A done sheet cannot be cancelled."))
        self.write({'state': 'cancelled'})

    def action_set_draft(self):
        for sheet in self:
            if sheet.state not in ('confirmed', 'cancelled'):
                raise UserError(_("Only confirmed or cancelled sheets can be reset to draft."))
        self.write({'state': 'draft'})

    def unlink(self):
        for sheet in self:
            if sheet.state not in ('draft', 'cancelled'):
                raise UserError(_("Only draft or cancelled sheets can be deleted."))
        return super().unlink()

    #  CRON  #

    @api.model
    def _cron_generate_monthly_sheets(self):
        """ During the first days of a month, create last month's sheet for every company.

        The cron runs daily and is idempotent: a sheet that already exists is never recreated.
        """
        today = fields.Date.context_today(self)
        if today.day > 5:
            return
        last_month = today.replace(day=1) - relativedelta(days=1)
        for company in self.env['res.company'].search([]):
            exists = self.search_count([
                ('company_id', '=', company.id),
                ('year', '=', last_month.year),
                ('month', '=', str(last_month.month)),
            ])
            if exists:
                continue
            sheet = self.create({
                'company_id': company.id,
                'year': last_month.year,
                'month': str(last_month.month),
            })
            sheet.action_generate_lines()


class HrAttendanceSheetLine(models.Model):
    _name = 'hr.attendance.sheet.line'
    _description = 'Monthly Attendance & Deduction Sheet Line'
    _order = 'employee_id'

    sheet_id = fields.Many2one(
        'hr.attendance.sheet', string="Sheet", required=True, ondelete='cascade', index=True
    )
    company_id = fields.Many2one(related='sheet_id.company_id', store=True)
    state = fields.Selection(related='sheet_id.state')
    employee_id = fields.Many2one('hr.employee', string="Employee", required=True)
    department_id = fields.Many2one(related='employee_id.department_id', store=True)

    # Figures read from attendances and time off (editable by HR before confirmation)
    scheduled_days = fields.Float(string="Working Days")
    present_days = fields.Float(string="Present")
    leave_days = fields.Float(string="Time Off")
    unpaid_leave_days = fields.Float(string="Unpaid Time Off")
    absent_days = fields.Float(string="Absent")
    late_count = fields.Integer(string="Late Arrivals")
    late_minutes = fields.Integer(string="Late (min)")
    ot_hours = fields.Float(string="Approved Overtime (h)")

    # Amounts
    monthly_gross = fields.Float(
        string="Monthly Gross",
        help="Salary base. Copied from the employee's wage when empty; editable here.",
    )
    late_deduction_days = fields.Float(compute='_compute_amounts', store=True, string="Late Penalty (days)")
    total_deduction_days = fields.Float(compute='_compute_amounts', store=True, string="Deduction (days)")
    deduction_amount = fields.Float(compute='_compute_amounts', store=True, string="Deduction")
    ot_amount = fields.Float(compute='_compute_amounts', store=True, string="Overtime Pay")
    net_adjustment = fields.Float(compute='_compute_amounts', store=True, string="Net Adjustment")
    note = fields.Char()

    _employee_uniq = models.Constraint(
        'unique(sheet_id, employee_id)', "An employee can only appear once per sheet."
    )

    #  COMPUTE METHODS  #

    @api.depends(
        'monthly_gross', 'late_count', 'absent_days', 'unpaid_leave_days', 'ot_hours',
        'sheet_id.company_id',
    )
    def _compute_amounts(self):
        rule_model = self.env['hr.attendance.rule']
        for line in self:
            rule = rule_model._get_rule(line.sheet_id.company_id or self.env.company)
            threshold = rule.late_count_threshold
            late_days = (line.late_count // threshold) * rule.late_cut_days if threshold else 0.0
            total_days = late_days + line.absent_days + line.unpaid_leave_days
            per_day = line.monthly_gross / rule.days_in_month if rule.days_in_month else 0.0
            per_hour = per_day / rule.hours_per_day if rule.hours_per_day else 0.0

            line.late_deduction_days = late_days
            line.total_deduction_days = total_days
            line.deduction_amount = total_days * per_day
            line.ot_amount = line.ot_hours * per_hour * rule.overtime_rate
            line.net_adjustment = line.ot_amount - line.deduction_amount

    #  FIGURES  #

    def _get_employee_gross(self):
        self.ensure_one()
        # In Odoo 19 the wage lives on the employee's version (former contract).
        return self.employee_id.sudo().version_id.wage or 0.0

    def _refresh_figures(self):
        """ Compute attendance and time off figures of the lines from the period of the sheet. """
        attendance_model = self.env['hr.attendance'].sudo()
        leave_model = self.env['hr.leave'].sudo()
        for sheet, lines in self.grouped('sheet_id').items():
            date_from, date_to = sheet.date_from, sheet.date_to
            employees = lines.employee_id
            # The search window is padded to absorb timezone shifts; days are filtered later.
            window_start = datetime.combine(date_from - timedelta(days=1), time.min)
            window_end = datetime.combine(date_to + timedelta(days=2), time.min)
            attendances = attendance_model.search([
                ('employee_id', 'in', employees.ids),
                ('check_in', '>=', window_start),
                ('check_in', '<', window_end),
            ]).grouped('employee_id')
            leaves = leave_model.search([
                ('employee_id', 'in', employees.ids),
                ('state', '=', 'validate'),
                ('request_date_from', '<=', date_to),
                ('request_date_to', '>=', date_from),
            ]).grouped('employee_id')
            for line in lines:
                line._refresh_one(
                    attendances.get(line.employee_id, attendance_model.browse()),
                    leaves.get(line.employee_id, leave_model.browse()),
                    date_from, date_to,
                )

    def _refresh_one(self, attendances, leaves, date_from, date_to):
        self.ensure_one()
        employee = self.employee_id.sudo()
        calendar = employee.resource_calendar_id or employee.company_id.resource_calendar_id
        tz = pytz.timezone(employee.tz or (calendar and calendar.tz) or 'UTC')

        # Attendance side: present days, late arrivals and approved overtime.
        present_dates, late_count, late_minutes, overtime = set(), 0, 0, 0.0
        for attendance in attendances:
            local_date = pytz.utc.localize(attendance.check_in).astimezone(tz).date()
            if not date_from <= local_date <= date_to:
                continue
            present_dates.add(local_date)
            if attendance.is_late:
                late_count += 1
                late_minutes += attendance.late_minutes
            overtime += attendance.validated_overtime_hours

        # Schedule side: working days of the month (weekends and public holidays excluded).
        scheduled_dates = set()
        if calendar and not employee.resource_id._is_flexible():
            start_dt = tz.localize(datetime.combine(date_from, time.min))
            end_dt = tz.localize(datetime.combine(date_to + timedelta(days=1), time.min))
            result = calendar._work_intervals_batch(start_dt, end_dt)
            for interval in next(iter(result.values()), []):
                scheduled_dates.add(interval[0].astimezone(tz).date())
        else:
            scheduled_dates = set(present_dates)  # Flexible schedule: nothing to be absent from.

        # Time off side: validated time off falling in the month.
        leave_dates, leave_days, unpaid_days = set(), 0.0, 0.0
        for leave in leaves:
            start = max(leave.request_date_from, date_from)
            end = min(leave.request_date_to, date_to)
            covered = {d for d in scheduled_dates if start <= d <= end}
            inside = leave.request_date_from >= date_from and leave.request_date_to <= date_to
            days = leave.number_of_days if inside else float(len(covered))
            leave_dates |= covered
            leave_days += days
            if leave.holiday_status_id.unpaid:
                unpaid_days += days

        today = fields.Date.context_today(self)
        absent_dates = {d for d in scheduled_dates if d < today} - present_dates - leave_dates
        self.write({
            'scheduled_days': len(scheduled_dates),
            'present_days': len(present_dates),
            'leave_days': leave_days,
            'unpaid_leave_days': unpaid_days,
            'absent_days': len(absent_dates),
            'late_count': late_count,
            'late_minutes': late_minutes,
            'ot_hours': overtime,
            'monthly_gross': self.monthly_gross or self._get_employee_gross(),
        })
