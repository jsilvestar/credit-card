from openerp import models, fields, api, _
from openerp.exceptions import except_orm, Warning, UserError
from lxml import etree
import braintree


class cim_create_customer_profile(models.TransientModel):
    _inherit = 'cim.create.customer.profile'

    def _prepare_customer(self):
        partner = self.partner_id or self.invoice_addr_id
        if ' ' in partner.name:
            parts = partner.name.split()
            firstname = parts[0]
            lastname = ' '.join(parts[1:])
        else:
            lastname = partner.name
            firstname = '-'
        values = {
            "first_name": firstname,
            "last_name": lastname,
            "company": partner.parent_id.name or '',
            "email": partner.email or '',
            "phone": partner.phone or '',
            "fax": partner.fax or '',
            "website": partner.website or ''
        }
        return values

    def _prepare_address(self, partner):
        cim_id = partner.cim_id
        if not cim_id:
            raise UserError(_('Customer Profile has no valid ID!'))

        if ' ' in partner.name:
            parts = partner.name.split()
            firstname = parts[0]
            lastname = ' '.join(parts[1:])
        else:
            lastname = partner.name
            firstname = ''
        return {
            "customer_id": cim_id.profile_id,
            "first_name": firstname,
            "last_name": lastname,
            "company": partner.parent_id.name or '',
            "street_address": partner.street or '',
            "extended_address": partner.street2 or '',
            "locality": partner.city or '',
            "region": partner.state_id.name or '',
            "postal_code": partner.zip or '',
            "country_name": partner.country_id.name or ''
        }

    def create_braintree_address(self, partner):
        self.env['credit.card.api']._configure_environment()

        # Generate the dictionary value to send to Braintree
        req_dict_obj = self._prepare_address(partner)

        res = braintree.Address.create(req_dict_obj)

        # Catch any weird remaining errors and tell the user to inform IT so we
        # can better parse fringe results
        if not res.is_success:
            raise Warning(res.message)

        # If we didn't raise an exception yet, we should have a valid profile ID to work with,
        # so create the profile and assign it to the partner
        partner.braintree_address_id = res.address.id

    @api.multi
    def send_request(self):
        cim_obj = self.env['customer.profile']

        # Preparing local customer profile record
        vals = {
            'name': self.name or self.invoice_addr_id.name,
            'partner_id': self.partner_id.id,
            'invoice_addr_id': self.invoice_addr_id.id,
        }
        cim_id = cim_obj.create(vals)

        # Link that customer profile to the partner
        self.partner_id.cim_id = cim_id.id

        self.env['credit.card.api']._configure_environment()

        # Generate the dictionary value to send to Braintree
        req_dict_obj = self._prepare_customer()

        res = braintree.Customer.create(req_dict_obj)

        # Catch any weird remaining errors and tell the user to inform IT so we
        # can better parse fringe results
        if not res.is_success:
            raise Warning(res.message)

        # If we didn't raise an exception yet, we should have a valid profile ID to work with,
        # so create the profile and assign it to the partner
        cim_id.profile_id = res.customer.id

        self.create_braintree_address(self.partner_id)
        return cim_id
