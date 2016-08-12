from openerp import models, fields, api, _


class ResPartner(models.Model):
    _inherit = 'res.partner'

    braintree_address_id = fields.Char()
