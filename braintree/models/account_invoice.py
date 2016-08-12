from openerp import models, fields, api, _
from werkzeug import url_encode


class Invoice(models.Model):
    _inherit = 'account.invoice'

    cim_id = fields.Many2one(related='partner_id.cim_id')
    cim_payment_id = fields.Many2one(
        'payment.profile', 'Credit Card',
        domain="[('cim_id','=',cim_id)]")
    card_declined_note = fields.Char('Card Decline Reason', copy=False)
    card_declined = fields.Boolean(
        help="Indicate the card decline status", copy=False)

    @api.multi
    def add_creditcard(self):
        self.ensure_one()
        if not self.partner_id.cim_id:
            self.env['customer.profile'].create_customer_profile(
                self.partner_id)
        values_to_pass = dict(self._context.get('params'))
        values_to_pass.update({
            'model': self._name,
            'id': self.id})
        final_url = "braintree/partner/%s/?%s" % (
            self.partner_id.id, url_encode(values_to_pass))

        return {'type': 'ir.actions.act_url', 'target': 'self', 'url': final_url}

    @api.multi
    def update_all_payment_methods(self):
        self.env['payment.profile'].update_all_payment_methods(self.partner_id)

    @api.multi
    def invoice_pay_customer(self):
        action = super(Invoice, self).invoice_pay_customer()
        if self.cim_payment_id:
            action['context'][
                'default_cim_payment_id'] = self.cim_payment_id.id
        return action
