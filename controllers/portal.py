from odoo import http
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


class EmployeePortal(CustomerPortal):
    """ Employees see their own time off and attendance in the portal (read only). """

    def _get_portal_employee(self):
        return request.env['hr.employee'].sudo().search(
            [('user_id', '=', request.env.uid)], limit=1
        )

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        employee = self._get_portal_employee()
        if 'hlap_leave_count' in counters:
            values['hlap_leave_count'] = request.env['hr.leave'].sudo().search_count(
                [('employee_id', '=', employee.id)]
            ) if employee else 0
        if 'hlap_attendance_count' in counters:
            values['hlap_attendance_count'] = request.env['hr.attendance'].sudo().search_count(
                [('employee_id', '=', employee.id)]
            ) if employee else 0
        return values

    @http.route(
        ['/my/leaves', '/my/leaves/page/<int:page>'], type='http', auth='user', website=True
    )
    def portal_my_leaves(self, page=1, **kw):
        employee = self._get_portal_employee()
        domain = [('employee_id', '=', employee.id)] if employee else [('id', '=', 0)]
        leave_model = request.env['hr.leave'].sudo()
        pager = portal_pager(
            url='/my/leaves',
            total=leave_model.search_count(domain),
            page=page,
            step=self._items_per_page,
        )
        leaves = leave_model.search(
            domain, order='date_from desc', limit=self._items_per_page, offset=pager['offset']
        )
        return request.render('hr_leave_attendance_plus.portal_my_leaves', {
            'leaves': leaves,
            'page_name': 'hlap_leaves',
            'pager': pager,
            'default_url': '/my/leaves',
        })

    @http.route(
        ['/my/attendance', '/my/attendance/page/<int:page>'], type='http', auth='user',
        website=True,
    )
    def portal_my_attendance(self, page=1, **kw):
        employee = self._get_portal_employee()
        domain = [('employee_id', '=', employee.id)] if employee else [('id', '=', 0)]
        attendance_model = request.env['hr.attendance'].sudo()
        pager = portal_pager(
            url='/my/attendance',
            total=attendance_model.search_count(domain),
            page=page,
            step=self._items_per_page,
        )
        attendances = attendance_model.search(
            domain, order='check_in desc', limit=self._items_per_page, offset=pager['offset']
        )
        return request.render('hr_leave_attendance_plus.portal_my_attendance', {
            'attendances': attendances,
            'page_name': 'hlap_attendance',
            'pager': pager,
            'default_url': '/my/attendance',
        })
