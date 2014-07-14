import unittest
from convoy.tests.adminscript import AdminScriptTestCase, test_dir


class ManageRunserverEmptyAllowedHosts(AdminScriptTestCase):
    def setUp(self):
        print "setting up..."
        # these are some simple defaults.
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

        self.assertNoOutput(err)
        print out
        
    def test_convoy_installedapp(self):
        self.write_settings('settings.py', 
            apps= [
                'django.contrib.admin',
                'django.contrib.auth',
                'django.contrib.contenttypes',
                'django.contrib.sessions',
                'django.contrib.messages',
                'django.contrib.staticfiles',
                'convoy',
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
                'STATICFILES_STORAGE': "'convoy.stores.ConvoyStorage'",
                'CONVOY_DURING_DEBUG': 'True',
                'CONVOY_AWS_QUERYSTRING_AUTH': 'False',
                'CARPOOL_COMBINE_DURING_DEBUG': 'True',
            }
        )
        self.cat_settings('settings.py')

        out, err = self.run_manage(['collectstatic', '--noinput'])


        self.assertNoOutput(err)
        print out