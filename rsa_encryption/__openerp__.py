# -*- coding: utf-8 -*-
# Copyright 2004-2013 OpenERP SA (<http://www.openerp.com>)
# Copyright 2013 Solaris, Inc. (<http://www.solarismed.com>)
# Copyright 2016 Sodexis, Inc. <dev@sodexis.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    'name': 'RSA Encryption',
    'version': '9.0.1.0.0',
    'depends': [
        'base'
    ],
    'author': 'Solaris',
    'website': 'http://solarismed.com',
    'category': 'Others',
    'data': [
        'security/ir.model.access.csv',
        'wizard/key_generator_view.xml',
        'views/rsa_view.xml',
    ],
    'installable': True,
}
