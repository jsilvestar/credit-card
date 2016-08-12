from openerp import models, fields, api
from openerp.exceptions import except_orm
from lxml import etree


class cim_create_customer_profile(models.TransientModel):
    _name = 'cim.create.customer.profile'

    name = fields.Char(
        'Name',
        size=255)
    partner_id = fields.Many2one(
        'res.partner',
        'Partner',
        required=True)
    invoice_addr_id = fields.Many2one(
        'res.partner',
        'Billing Contact',
        domain="['|',('parent_id','=',partner_id),('id','=',partner_id)]",
        required=True,
        help="This contact will be used to register the billing information.")
    profile_id = fields.Char(
        'Customer Profile ID',
        size=32)
    manual = fields.Boolean()

    @api.onchange('invoice_addr_id')
    def onchange_invoice(self):
        if self.invoice_addr_id:
            partner = self.invoice_addr_id
            name = partner.name
            if partner.parent_id:
                name = partner.parent_id.name + ', ' + name
            self.name = name

    @api.multi
    def add_existing_customer_profile(self):
        cim_obj = self.env['customer.profile']

        # Preparing local customer profile record
        vals = {
            'name': self.name or self.invoice_addr_id.name,
            'partner_id': self.partner_id.id,
            'invoice_addr_id': self.invoice_addr_id.id,
            'profile_id': self.profile_id,
        }
        cim_id = cim_obj.create(vals)

        self.partner_id.cim_id = cim_id.id
        return True
