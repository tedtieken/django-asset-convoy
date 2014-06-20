import unittest
from convoy.tests.adminscript import AdminScriptTestCase


class ManageRunserverEmptyAllowedHosts(AdminScriptTestCase):
    def setUp(self):
        print "setting up..."

        # this is not properly setting these things up
        self.write_settings('settings.py', sdict={
            'ALLOWED_HOSTS': [],
            'DEBUG': False,
            'DATABASES': {
                'default': {
                    'ENGINE': 'django.db.backends.sqlite3'
                },
                'other': {
                    'ENGINE': 'django.db.backends.sqlite3',
                }
            },
        })


    def tearDown(self):
        self.remove_settings('settings.py')

    def test_empty_allowed_hosts_error(self):
        out, err = self.run_manage(['runserver'])
        self.assertNoOutput(out)
        self.assertOutput(err, 'CommandError: You must set settings.ALLOWED_HOSTS if DEBUG is False.')

    def test_collectstatic(self):

        self.write_settings('settings.py', sdict={
            'STATIC_ROOT': "'/static/'",
            'STATIC_URL': "'/static/'"
            })
        out, err = self.run_manage(['collectstatic'])
        self.assertNoOutput(err)
        print out

