# -*- coding: utf-8 -*-
# Copyright 2004-2013 OpenERP SA (<http://www.openerp.com>)
# Copyright 2013 Solaris, Inc. (<http://www.solarismed.com>)
# Copyright 2016 Sodexis, Inc. <dev@sodexis.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Hash import SHA
from Crypto import Random
import base64

from openerp import models, fields, api, _
from openerp.exceptions import UserError


class RsaEncryption(models.Model):
    _name = 'rsa.encryption'
    _description = 'Portable RSA encryption for custom OpenERP code'

    name = fields.Char('Private Key Name', size=64, required=True)
    pub_name = fields.Char('Public Key Name')
    active = fields.Boolean('Active')
    primary = fields.Boolean(
        'Primary',
        readonly=True,
        help="Only one primary key should be selected at a time.")

    # Return both keys at once as a tuple:
    # 	(<pkey object>, <pubkey object>)
    @api.model
    def get_keys(self):
        primary_keys = self.search(
            [('primary', '=', True), ('active', '=', True)], limit=1)
        if not primary_keys:
            raise UserError(
                _("No primary key set available for use. "
                  "Generate a new set or flag an existing set as primary."))
        key_rec = primary_keys[0]
        pkey = RSA.importKey(open(key_rec.name, 'r').read())
        pubkey = RSA.importKey(open(key_rec.pub_name, 'r').read())
        return (pkey, pubkey)

    @api.model
    def get_pubkey(self):
        primary_keys = self.search(
            [('primary', '=', True), ('active', '=', True)], limit=1)
        if not primary_keys:
            raise UserError(
                _("No primary key set available for use. "
                  "Generate a new set or flag an existing set as primary."))
        key_rec = primary_keys[0]
        return RSA.importKey(open(key_rec.pub_name, 'r').read())

    @api.model
    def get_privkey(self):
        primary_keys = self.search(
            [('primary', '=', True), ('active', '=', True)], limit=1)
        if not primary_keys:
            raise UserError(_("No primary key set for use."))
        key_rec = primary_keys[0]
        return RSA.importKey(open(key_rec.name, 'r').read())

    @api.model
    def encrypt(self, value, key=False):
        if not isinstance(value, str):
            value = str(value)
        if not key:
            key = self.get_pubkey()
        h = SHA.new(value)
        cipher = PKCS1_v1_5.new(key)
        res = base64.encodestring(cipher.encrypt(value + h.digest()))
        return res

    @api.model
    def decrypt(self, value, key=False):
        if not key:
            key = self.get_privkey()
        dsize = SHA.digest_size
        sentinel = Random.new().read(15 + dsize)
        cipher = PKCS1_v1_5.new(key)
        res = cipher.decrypt(base64.decodestring(value), sentinel)

        # Validate results
        digest = SHA.new(res[:-dsize]).digest()
        if digest == res[-dsize:]:
            return res[:-dsize]
        else:
            return False

    # -----------------------
    # ORM data prep functions
    # -----------------------
    # Use these to quickly and properly account for read/write/create/copy encryption and decryption
    # Doesn't call ORM directly, just cleans the secured values for proper
    # writing or reading
    @api.model
    def rsa_create(self, values, secure_fields):
        pubkey = self.get_pubkey()

        # Iterate through the list of secured fields and encrypt them
        for secure_field in secure_fields:
            if values.get(secure_field, False):
                values[secure_field] = self.encrypt(
                    values[secure_field], pubkey)

        # Return values to create with secure fields properly encrypted
        return values

    # Decrypt a read on the first record if context['unmask'] exists and is True
    # No support for batch decryption at the moment - could be added with
    # context if needed
    @api.model
    def rsa_read(self, values, secure_fields):
        pkey = self.get_privkey()

        # If read values is a dictionary, not a list, respect that read format
        if not isinstance(values, list):
            for secure_field in secure_fields:
                if values.get(secure_field, False):
                    if self._context.get('unmask', False):
                        values[secure_field] = self.decrypt(
                            values[secure_field], key=pkey)
                    # TODO: bad workaround for finding last 4 digits of CC and
                    # decrypting!  Not abstracted properly
                    elif self._context.get('cc_last_four', False) and secure_field == 'cc_number':
                        decode = self.decrypt(values[secure_field], pkey)
                        values[secure_field] = 'xxxxxxxxxxxx' + decode[-4:]
                        del decode
                    else:
                        values[secure_field] = 'xxxx'

        # If read values is a list of dictionaries, respect that read format and only operate on the first entry
        # to avoid needless work on list views where read() is called and will
        # return potentially hundreds of items
        elif len(values) == 1:
            for secure_field in secure_fields:
                if values[0].get(secure_field, False):
                    if self._context.get('unmask', False):
                        values[0][secure_field] = self.decrypt(
                            values[0][secure_field], key=pkey)
                    elif self._context.get('cc_last_four', False) and secure_field == 'cc_number':
                        decode = self.decrypt(values[0][secure_field], pkey)
                        values[0][secure_field] = 'xxxxxxxxxxxx' + decode[-4:]
                        del decode
                    else:
                        values[0][secure_field] = 'xxxx'
        return values

    # Avoid writing in masked fields by looking for the 'xxxx' mask
    @api.model
    def rsa_write(self, values, secure_fields):
        pubkey = self.get_pubkey()

        for secure_field in secure_fields:
            # If it's a secured field and it's set to something other than the
            # mask values, re-encrypt it
            if values.get(secure_field, False) and values[
                    secure_field][:4] != 'xxxx':
                values[secure_field] = self.encrypt(
                    values[secure_field], pubkey)
        return values

    # Always strip out encrypted fields when duplicating
    @api.model
    def rsa_copy(self, values, secure_fields):
        for secure_field in secure_fields:
            if values.get(secure_field, False):
                values[secure_field] = False
        return values
