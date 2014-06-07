import unittest
from convoy.tests.adminscript import AdminScriptTestCase

print AdminScriptTestCase

# Create your tests here.

class Derp(unittest.TestCase):
    def test_derp(self):
        assert 2 == 1+1

class ManageRunserverEmptyAllowedHosts(AdminScriptTestCase):
    def setUp(self):
        print "setting up..."
        self.write_settings('settings.py', sdict={
            'ALLOWED_HOSTS': [],
            'DEBUG': False,
            'DATABASES': [],
        })

    def tearDown(self):
        self.remove_settings('settings.py')

    def test_empty_allowed_hosts_error(self):
        out, err = self.run_manage(['runserver'])
        self.assertNoOutput(out)
        self.assertOutput(err, 'CommandError: You must set settings.ALLOWED_HOSTS if DEBUG is False.')



