Portable RSA Encryption
=======================

An Odoo object containing RSA encryption and decryption methods that are PKCS#1 v1.5 compliant.
Can be utilized by any module, just set the dependency on this module and use
"rsa = self.env['rsa.encryption']" in your code to access the functions.  This code implements
the Python Crypto library (pycrypto).  See full documentation here:  https://pypi.python.org/pypi/pycrypto

To begin, you must generate a set of keys from 'Settings' -> 'Technical' -> 'Security' -> 'Generate New Keys'.
The files will be saved in the server root directory (where odoo.py is) and given read/write
permission ONLY to the owner - whichever account is running Odoo.

Ensure that any module using this code adds 'rsa_encryption' as a dependency!.  Also make sure anything
you store encrypted in the database is defined as a char field with a size of at least 512 characters
(based on a 2048-bit key).


Functions
=========
rsa = self.env['rsa.encryption']
	Get the RSA object, must always be done first.

rsa.get_keys()
	Returns a tuple of the private key and public key objects in that order.  Will only ever return the
	"primary" key defined in OpenERP, so you don't need to search for the key record first.  Should only be
	called for efficiency, pass the correct key to the encrypt and decrypt functions to avoid re-reading the
	key from the disk every time.

rsa.get_pubkey()
	Returns the public key object from the primary set.  Use this to avoid multiple reads from the disk for
	multiple sequential encrypt() calls.

rsa.get_privkey()
	Returns the private key object from the primary set.  Use this to avoid multiple reads from the disk for
	multiple sequential decrypt() calls.

rsa.encrypt(value, key=False)
	Returns a base64 encoded string of the value encrypted.  Will use the key object if passed, otherwise will
	call get_pubkey().

rsa.decrypt(value, key=False)
	Returns the decoded content of the encrypted value.  The value should be a base64 encoded string from
	encrypt().  Will use the key object if passed, otherwise will call get_privkey().