from openerp import models, fields, api
from openerp.exceptions import except_orm
from lxml import etree


class cim_create_customer_profile(models.TransientModel):
    _inherit = 'cim.create.customer.profile'

    @api.multi
    def _prepare_xml(self):
        root = self.env['credit.card.api']._get_xml_header(
            'createCustomerProfileRequest',
            refId=False)
        profile = etree.SubElement(root, 'profile')
        etree.SubElement(
            profile, 'merchantCustomerId').text = str(self.partner_id.id)
        etree.SubElement(profile, 'description').text = self.name

        if self.invoice_addr_id.email:
            etree.SubElement(
                profile,
                'email').text = self.invoice_addr_id.email
        elif self.partner_id.email:
            etree.SubElement(
                profile,
                'email').text = self.partner_id.email

        return root

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

        # Generate the XML object
        req_xml_obj = self._prepare_xml()

        print "\nSending:\n\n", etree.tostring(req_xml_obj, pretty_print=True), "\n"

        # Send the XML object to Authorize.net and return the XML string
        res = self.env['credit.card.api']._send_request(req_xml_obj)

        # If we've returned, the XML must be good.  Look for a customer profile
        # ID assigned by auth.net
        profile_id_path = res.xpath("//customerProfileId")

        # Catch any weird remaining errors and tell the user to inform IT so we
        # can better parse fringe results
        if not profile_id_path or not profile_id_path[0].text or len(profile_id_path) > 1:
            self._cr.rollback()
            errormsg = "Did not find the tag <customerProfileId> in the XML, but also did not detect an error.  Please copy the following response data and notify IT of this problem.\n\n%s" % etree.tostring(
                res, pretty_print=True)
            raise except_orm("XML Error", errormsg)

        # If we didn't raise an exception yet, we should have a valid profile ID to work with,
        # so create the profile and assign it to the partner
        cim_id.profile_id = profile_id_path[0].text
        return cim_id
