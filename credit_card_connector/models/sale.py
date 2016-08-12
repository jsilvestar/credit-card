
from openerp import models, fields, api, _
from openerp import netsvc


class sale_order(models.Model):
    _inherit = 'sale.order'

    @api.multi
    def _prepare_invoice(self):
        invoice_vals = super(sale_order, self)._prepare_invoice()
        if self.payment_term_id:
            invoice_vals['is_cc_payment'] = self.payment_term_id.is_cc_term
        return invoice_vals
