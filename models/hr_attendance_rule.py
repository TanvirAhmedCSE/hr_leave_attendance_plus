from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HrAttendanceRule(models.Model):
    """ Company-level rules: approval thresholds, late policy and salary-deduction parameters. """
    _name = 'hr.attendance.rule'
    _description = 'Leave & Attendance Rules'

    name = fields.Char(required=True, default="Leave & Attendance Rules")
    company_id = fields.Many2one(
        'res.company', string="Company", required=True, default=lambda self: self.env.company
    )

    # Time off approval chain
    level2_days = fields.Float(
        string="HR Approval Above (days)", default=3.0,
        help="Time off longer than this needs the HR approval after the Line Manager.",
    )
    level3_days = fields.Float(
        string="MD Approval Above (days)", default=7.0,
        help="Time off longer than this also needs the final approval of the Managing Director.",
    )
    enforce_distinct_approvers = fields.Boolean(
        string="Distinct Approvers",
        help="If enabled, the same user cannot approve two levels of the same time off.",
    )
    reminder_days = fields.Integer(
        string="Reminder After (days)", default=2,
        help="A reminder activity is sent to the current approvers after this many days.",
    )

    # Late policy
    grace_minutes = fields.Integer(string="Grace Period (minutes)", default=10)
    late_count_threshold = fields.Integer(
        string="Late Days per Penalty", default=3,
        help="Number of late arrivals in a month that trigger one penalty.",
    )
    late_cut_days = fields.Float(
        string="Penalty (days of salary)", default=1.0,
        help="Days of salary deducted for each group of late arrivals.",
    )

    # Salary base
    days_in_month = fields.Integer(string="Days in Month (salary base)", default=30)
    hours_per_day = fields.Float(string="Working Hours per Day", default=8.0)
    overtime_rate = fields.Float(
        string="Overtime Rate Multiplier", default=2.0,
        help="Overtime hours are paid at this multiple of the normal hourly rate.",
    )

    _company_uniq = models.Constraint(
        'unique(company_id)', "There can be only one set of rules per company."
    )

    @api.constrains('level2_days', 'level3_days')
    def _check_levels(self):
        for rule in self:
            if rule.level3_days < rule.level2_days:
                raise ValidationError(_("The MD threshold must not be lower than the HR threshold."))

    @api.model
    def _get_rule(self, company=None):
        """ Return the rules of the company, creating the default ones when missing. """
        company = company or self.env.company
        rule = self.sudo().search([('company_id', '=', company.id)], limit=1)
        return rule or self.sudo().create({'company_id': company.id})
