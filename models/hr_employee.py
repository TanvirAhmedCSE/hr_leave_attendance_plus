from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    late_count_month = fields.Integer(
        string="Late Arrivals (month)", compute='_compute_late_count_month'
    )

    def _compute_late_count_month(self):
        month_start = fields.Date.context_today(self).replace(day=1)
        counts = dict(self.env['hr.attendance'].sudo()._read_group(
            [
                ('employee_id', 'in', self.ids),
                ('is_late', '=', True),
                ('check_in', '>=', month_start),
            ],
            groupby=['employee_id'],
            aggregates=['__count'],
        ))
        for employee in self:
            employee.late_count_month = counts.get(employee, 0)

    def action_view_late_attendance(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("Late Arrivals"),
            'res_model': 'hr.attendance',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.id), ('is_late', '=', True)],
            'context': {'default_employee_id': self.id},
        }
