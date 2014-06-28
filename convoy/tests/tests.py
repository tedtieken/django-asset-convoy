import unittest
from convoy.tests.adminscript import AdminScriptTestCase, test_dir


class ManageRunserverEmptyAllowedHosts(AdminScriptTestCase):
    def setUp(self):
        print "setting up..."
        self.write_settings('settings.py', 
            apps= [
                'django.contrib.admin',
                'django.contrib.auth',
                'django.contrib.contenttypes',
                'django.contrib.sessions',
                'django.contrib.messages',
                'django.contrib.staticfiles',
            ],
            sdict={
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
            }
        )
        # this is not properly setting these things up



    def tearDown(self):
        self.remove_settings('settings.py')

    def test_empty_allowed_hosts_error(self):
        out, err = self.run_manage(['runserver'])
        self.assertNoOutput(out)
        self.assertOutput(err, 'CommandError: You must set settings.ALLOWED_HOSTS if DEBUG is False.')

    def test_collectstatic(self):
        self.write_settings('settings.py', 
            apps= [
                'django.contrib.admin',
                'django.contrib.auth',
                'django.contrib.contenttypes',
                'django.contrib.sessions',
                'django.contrib.messages',
                'django.contrib.staticfiles',
            ],
            sdict={
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
                'STATIC_ROOT': "'static/'",
                'STATIC_URL': "'/static/'",
            }
        )
        self.cat_settings('settings.py')
        print test_dir

        out, err = self.run_manage(['collectstatic', '--noinput'])

        # import ipdb
        # ipdb.set_trace()


        self.assertNoOutput(err)
        print out
        