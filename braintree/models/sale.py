from braintree import Customer, PaymentMethod

from openerp import models, fields, api, _
from openerp.exceptions import Warning
from werkzeug import url_encode


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    cim_id = fields.Many2one(related='partner_invoice_id.cim_id')
    cim_payment_id = fields.Many2one(
        'payment.profile', 'Credit Card',
        domain="[('cim_id','=',cim_id)]",
        help='Lists the credit cards of Invoice Address selected')

    @api.multi
    def add_creditcard(self):
        self.ensure_one()
        if not self.partner_invoice_id.cim_id:
            self.env['customer.profile'].create_customer_profile(
                self.partner_invoice_id)
        values_to_pass = dict(self._context.get('params'))
        values_to_pass.update({
            'model': self._name,
            'id': self.id})
        final_url = "braintree/partner/%s/?%s" % (
            self.partner_invoice_id.id, url_encode(values_to_pass))

        return {'type': 'ir.actions.act_url', 'target': 'self', 'url': final_url}

    @api.multi
    def update_all_payment_methods(self):
        self.env['payment.profile'].update_all_payment_methods(
            self.partner_invoice_id)

    def _prepare_invoice(self):
        invoice_vals = super(SaleOrder, self)._prepare_invoice()
        invoice_vals['cim_payment_id'] = self.cim_payment_id.id or False
        invoice_vals['is_cc_payment'] = self.cim_payment_id and True or False
        return invoice_vals

    @api.onchange('partner_invoice_id')
    def onchange_partner_invoice_id(self):
        if self.partner_invoice_id.cim_id:
            self.update_all_payment_methods()
        self.cim_payment_id = self.cim_id.default_payprofile_id or self.cim_id.payprofile_ids.id

    @api.multi
    def action_confirm(self):
        if self.cim_payment_id:
            self.env['credit.card.api']._configure_environment()
            if not self.cim_id.partner_id.braintree_address_id:
                self.env['cim.create.customer.profile'].create_braintree_address(self.cim_id.partner_id)
            result = PaymentMethod.update(self.cim_payment_id.payprofile_id, {
                "billing_address_id": self.cim_id.partner_id.braintree_address_id,
                "options": {
                    "verify_card": True
                }
            })
            if not result.is_success:
                message = result.message
                if result.credit_card_verification:
                    message = '%s\n Verification response code: %s\n Verification response text: %s' % (
                        result.message,
                        result.credit_card_verification.processor_response_code,
                        result.credit_card_verification.processor_response_text
                    )
                raise Warning(message)
        return super(SaleOrder, self).action_confirm()
