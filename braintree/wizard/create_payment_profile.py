from openerp import models, fields, api, _
from openerp.exceptions import except_orm, Warning, UserError
from lxml import etree
import braintree
ENCRYPTED_FIELDS = ['cc_number', 'cc_cvv']


class cim_create_payment_profile(models.TransientModel):
    _inherit = 'cim.create.payment.profile'

    cardholder_name = fields.Char(size=50, required=True, copy=False)

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

    def _prepare_credit_card(self):
        cc_info_read = self.read(ENCRYPTED_FIELDS)[0]
        values = {
            "cardholder_name": self.cardholder_name,
            "customer_id": self.cim_id.profile_id,
            "number": cc_info_read['cc_number'],
            "cvv": cc_info_read['cc_cvv'],
            "expiration_month": self.cc_exp_month,
            "expiration_year": self.cc_exp_year,
            #"billing_address": self._prepare_address(self.alt_invoice_addr_id or self.partner_id.cim_id.invoice_addr_id or self.partner_id),
            "options": {
                "make_default": True,
                "verify_card": True,
            }
        }
        return values

    @api.multi
    def send_request(self):
        self = self.with_context(unmask=True)
        if not self.cim_id.profile_id:
            raise UserError(_('Customer Profile has no valid ID!'))

        cc_info_read = self.read(ENCRYPTED_FIELDS)[0]

        # Generate document regarding payment profile
        name = self.name or self.alt_invoice_addr_id and self.alt_invoice_addr_id.name or self.cim_id.invoice_addr_id.name or False
        vals = {
            'name': name,
            'cim_id': self.cim_id.id,
            'last_four': cc_info_read['cc_number'][-4:],
            'cc_exp_month': self.cc_exp_month,
            'cc_exp_year': self.cc_exp_year,
        }
        if self.alt_invoice_addr_id:
            vals['alt_invoice_addr_id'] = self.alt_invoice_addr_id.id
        cim_pay_obj = self.env['payment.profile']
        cim_pay_obj_id = cim_pay_obj.create(vals)

        self.env['credit.card.api']._configure_environment()

        # Generate the dictionary value to send to Braintree
        req_dict_obj = self._prepare_credit_card()

        res = braintree.CreditCard.create(req_dict_obj)

        # Catch any weird remaining errors and tell the user to inform IT so we
        # can better parse fringe results
        if not res.is_success:
            raise Warning(res.message)

        # If we didn't raise an exception yet, we should have a valid payment profile ID to work with,
        # so provide payprofile_id value Payment profile object created before
        # sending request
        cim_pay_obj_id.payprofile_id = res.credit_card.token
#         cim_pay_obj_id.masked_number = res.credit_card.masked_number
#         cim_pay_obj_id.unique_number_identifier = res.credit_card.unique_number_identifier

        return cim_pay_obj_id
