# -*- coding: utf-8 -*-
# Copyright 2004-2013 OpenERP SA (<http://www.openerp.com>)
# Copyright 2013 Solaris, Inc. (<http://www.solarismed.com>)
# Copyright 2016 Sodexis, Inc. <dev@sodexis.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from Crypto.PublicKey import RSA

from openerp import api, models, fields, _
from openerp.exceptions import UserError


class KeyGenerator(models.TransientModel):
    _name = 'key.generator'

    @api.model
    def _get_current_path(self):
        import os
        return os.getcwd()

    server_path = fields.Char(
        'Key Folder Path',
        size=256,
        required=True,
        default=_get_current_path,
        help="Typically this would be your root server path, but any folder "
        "that allows write access to the system user running OpenERP will work. "
        "Example:\n\n/opt/openerp/server")
    filename_priv = fields.Char(
        'Private Key Name',
        size=64,
        required=True
    )
    filename_pub = fields.Char(
        'Public Key Name',
        size=64,
        required=True
    )
    key_size = fields.Selection(
        [('1024', '1024'),
         ('2048', '2048'),
         ('4096', '4096'),
         ('8192', '8192')],
        'Key Length in bits',
        required=True,
        default='2048'
    )

    # Set the public key to <filename_priv>.pub
    @api.onchange('filename_priv')
    def onchange_private(self):
        if not self.filename_priv:
            self.filename_pub = ''
        else:
            self.filename_pub = self.filename_priv + '.pub'

    # key size (default 2048)
    @api.multi
    def generate_keys(self):
        # Make sure the filenames aren't blank or bad
        if self.filename_priv == self.filename_pub:
            raise UserError(
                _("The public and private key filenames are identical, "
                  "please choose different names."))

        import os
        # Parse server path and generate full file names
        # If the path doesn't end with a slash, add it
        if not os.path.exists(self.server_path):
            raise UserError(
                _("The path entered does not exist. "
                  "Please check the exact spelling and try again."))

        file_priv = os.path.join(
            self.server_path, self.filename_priv)
        file_pub = os.path.join(self.server_path,
                                self.filename_pub)

        pkey = RSA.generate(int(self.key_size))
        pubkey = pkey.publickey()

        # Raise OSV exceptions if the files exist - we shouldn't be overwriting an existing RSA key or
        # the data already encrypted using it will be forever lost!
        if os.path.isfile(file_priv):
            raise UserError(
                _("The private key already exists. "
                  "Please choose a different filename."))
        if os.path.isfile(file_pub):
            raise UserError(
                _("The public key already exists. "
                  "Please choose a different filename."))

        try:
            # Create the file, export the key, and set the permissions to
            # Read/Write for the owner ONLY
            f = open(file_priv, 'w')
            f.write(pkey.exportKey())
            f.close()
            os.chmod(file_priv, 0o600)

            # Repeat for public key, though this could arguably be 0644
            # instead.
            fpub = open(file_pub, 'w')
            fpub.write(pubkey.exportKey())
            fpub.close()
            os.chmod(file_pub, 0o600)
        except IOError:
            raise UserError(
                _("IOError raised while writing keys. "
                  "Check that the system user running the OpenERP server "
                  "has write permission on the folder\n\n%s" % self.server_path))

        rsa_obj = self.env['rsa.encryption']

        # Find any existing active key sets, if none exist, make it the primary
        # set
        make_primary = True
        found_keys = rsa_obj.search([('primary', '=', True)])
        if found_keys:
            make_primary = False
        vals = {
            'name': file_priv,
            'pub_name': file_pub,
            'active': True,
            'primary': make_primary,
        }
        rsa_obj.create(vals)

        return {
            'name': 'RSA Keys',
            'type': 'ir.actions.act_window',
            'res_model': 'rsa.encryption',
            'view_type': 'form',
            'view_mode': 'tree,form',
        }
