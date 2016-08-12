from openerp import models, fields, api


class res_partner(models.Model):
    _inherit = 'res.partner'

    cim_id = fields.Many2one(
        'customer.profile',
        string='Customer Profile',
        domain="[('partner_id','=',id)]",
        copy=False,
        help="The customer profile available in the Payment processing site")

    @api.model
    def _commercial_fields(self):
        res = super(res_partner, self)._commercial_fields()
        return res + ['cim_id']

    # Launches the wizard to create a customer profile for the CIM
    @api.multi
    def create_customer_profile(self):
        if self.cim_id:
            return {}

        addrs = self.env['res.partner'].address_get(['invoice'])
        default_invoice_addr_id = addrs.get('invoice', False) and addrs['invoice'] or \
            addrs.get('default', False) and addrs['default'] or \
            False
        self = self.with_context(
            {'default_partner_id': self.id, 'default_invoice_addr_id': default_invoice_addr_id})

        view_name = 'Create a Customer Profile'
        if self._context.get('default_manual', False):
            view_name = 'Add an Existing Customer Profile'
        return {
            'name': view_name,
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'cim.create.customer.profile',
            'type': 'ir.actions.act_window',
            'target': 'new',
            'context': self._context,
        }

    # Launches the wizard to create a payment profile to link to this customer
    @api.multi
    def create_payment_profile(self):

        if not self.cim_id:
            return {}

        self = self.with_context({
            'default_partner_id': self.id,
            'default_cim_id': self.cim_id.id,
            'default_alt_invoice_addr_id': self.id,
            'cc_last_four': True
        })

        return {
            'name': 'Register a Payment Profile',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'cim.create.payment.profile',
            'type': 'ir.actions.act_window',
            'target': 'new',
            'context': self._context,
        }
