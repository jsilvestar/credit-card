from openerp import models, fields, api
from openerp.exceptions import except_orm, Warning
from lxml import etree
ENCRYPTED_FIELDS = ['cc_number']


class cim_create_payment_profile(models.TransientModel):
    _inherit = 'cim.create.payment.profile'

    @api.multi
    def _prepare_xml(self):
        root = self.env['credit.card.api']._get_xml_header(
            'createCustomerPaymentProfileRequest',
            refId=False)
        etree.SubElement(
            root, 'customerProfileId').text = self.cim_id.profile_id

        # Define the record to pull from - either the default or the
        # alternative
        inv_rec = self.alt_invoice_addr_id or self.cim_id.invoice_addr_id or False
        if not inv_rec:
            raise Warning(
                "No invoicing contact listed in the payment profile or the customer profile.")

        payprofile = etree.SubElement(root, 'paymentProfile')
        etree.SubElement(
            payprofile, 'customerType').text = (
            inv_rec.is_company or inv_rec.parent_id) and 'business' or 'individual'

        # Billing info
        billto = etree.SubElement(payprofile, 'billTo')
        if self.bill_firstname:
            etree.SubElement(
                billto, 'firstName').text = self.bill_firstname
        if self.bill_lastname:
            etree.SubElement(
                billto, 'lastName').text = self.bill_lastname
        etree.SubElement(billto, 'company').text = self.partner_id.name
        if self.bill_street:
            etree.SubElement(billto, 'address').text = self.bill_street
        if inv_rec.city:
            etree.SubElement(billto, 'city').text = inv_rec.city
        if inv_rec.state_id:
            etree.SubElement(billto, 'state').text = inv_rec.state_id.code
        if inv_rec.zip:
            etree.SubElement(billto, 'zip').text = inv_rec.zip
        if inv_rec.phone:
            etree.SubElement(billto, 'phoneNumber').text = inv_rec.phone
        if inv_rec.fax:
            etree.SubElement(billto, 'faxNumber').text = inv_rec.fax

        # Credit card info
        payment = etree.SubElement(payprofile, 'payment')
        cc = etree.SubElement(payment, 'creditCard')
        self = self.with_context(unmask=True)
        cc_info_read = self.read(ENCRYPTED_FIELDS)[0]
        etree.SubElement(cc, 'cardNumber').text = cc_info_read['cc_number']
        del cc_info_read

        # Auth.net CIM requires YYYY-MM formatting, unlike the AIM.  Keeping the layout consistent
        # with what credit cards actually say and just manually making the year
        # 4 characters
        cc_year = self.cc_exp_year
        if len(cc_year) == 2:
            cc_year = '20' + cc_year
        etree.SubElement(
            cc, 'expirationDate').text = cc_year + '-' + self.cc_exp_month

        return root

    @api.multi
    def send_request(self):
        if not self._ids:
            raise Warning(
                'Error in processing the wizard, no record created.')

        self = self.with_context(unmask=True)
        if not self.cim_id.profile_id:
            raise Warning('Customer Profile has no valid ID!')

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

        # Generate the XML object
        req_xml_obj = self._prepare_xml()

        print "\nSending:\n\n", etree.tostring(req_xml_obj), "\n"

        # Send the XML object to Authorize.net and return the XML string
        res = self.env['credit.card.api']._send_request(req_xml_obj)

        # If we've returned, the XML must be good.  Look for a customer profile
        # ID assigned by auth.net
        profile_id_path = res.xpath("//customerPaymentProfileId")

        # Catch any weird remaining errors and tell the user to inform IT so we
        # can better parse fringe results
        if not profile_id_path or not profile_id_path[0].text or len(profile_id_path) > 1:
            self._cr.rollback()
            errormsg = "Did not find the tag <customerPaymentProfileId> in the XML, but also did not detect an error.  Please copy the following response data and notify IT of this problem.\n\n%s" % etree.tostring(
                res,
                pretty_print=True)
            raise except_orm("XML Error", errormsg)

        # If we didn't raise an exception yet, we should have a valid payment profile ID to work with,
        # so provide payprofile_id value Payment profile object created before
        # sending request
        cim_pay_obj_id.payprofile_id = profile_id_path[0].text

        return cim_pay_obj_id
