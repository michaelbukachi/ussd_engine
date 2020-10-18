from unittest import TestCase
from simplekv.fs import FilesystemStore
from ussd.session_store import SessionStore, SESSION_COOKIE_AGE
from datetime import datetime, timedelta
from freezegun import freeze_time
import uuid


class SessionTest(object):
    class SessionTestsMixin(TestCase):

        def backend(self, session_key=None) -> SessionStore:
            raise NotImplemented

        def setUp(self):
            self.session = self.backend()

        def tearDown(self):
            # NB: be careful to delete any sessions created; stale sessions fill up
            # the /tmp (with some backends) and eventually overwhelm it after lots
            # of runs (think buildbots)
            self.session.delete()

        def test_new_session(self):
            self.assertIs(self.session.modified, False)
            self.assertIs(self.session.accessed, False)

        def test_get_empty(self):
            self.assertIsNone(self.session.get('cat'))

        def test_store(self):
            self.session['cat'] = "dog"
            self.assertIs(self.session.modified, True)
            self.assertEqual(self.session.pop('cat'), 'dog')

        def test_pop(self):
            self.session['some key'] = 'exists'
            # Need to reset these to pretend we haven't accessed it:
            self.accessed = False
            self.modified = False

            self.assertEqual(self.session.pop('some key'), 'exists')
            self.assertIs(self.session.accessed, True)
            self.assertIs(self.session.modified, True)
            self.assertIsNone(self.session.get('some key'))

        def test_pop_default(self):
            self.assertEqual(self.session.pop('some key', 'does not exist'),
                             'does not exist')
            self.assertIs(self.session.accessed, True)
            self.assertIs(self.session.modified, False)

        def test_pop_default_named_argument(self):
            self.assertEqual(self.session.pop('some key', default='does not exist'), 'does not exist')
            self.assertIs(self.session.accessed, True)
            self.assertIs(self.session.modified, False)

        def test_pop_no_default_keyerror_raised(self):
            with self.assertRaises(KeyError):
                self.session.pop('some key')

        def test_setdefault(self):
            self.assertEqual(self.session.setdefault('foo', 'bar'), 'bar')
            self.assertEqual(self.session.setdefault('foo', 'baz'), 'bar')
            self.assertIs(self.session.accessed, True)
            self.assertIs(self.session.modified, True)

        def test_update(self):
            self.session.update({'update key': 1})
            self.assertIs(self.session.accessed, True)
            self.assertIs(self.session.modified, True)
            self.assertEqual(self.session.get('update key', None), 1)

        def test_has_key(self):
            self.session['some key'] = 1
            self.session.modified = False
            self.session.accessed = False
            self.assertIn('some key', self.session)
            self.assertIs(self.session.accessed, True)
            self.assertIs(self.session.modified, False)

        def test_values(self):
            self.assertEqual(list(self.session.values()), [])
            self.assertIs(self.session.accessed, True)
            self.session['some key'] = 1
            self.session.modified = False
            self.session.accessed = False
            self.assertEqual(list(self.session.values()), [1])
            self.assertIs(self.session.accessed, True)
            self.assertIs(self.session.modified, False)

        def test_keys(self):
            self.session['x'] = 1
            self.session.modified = False
            self.session.accessed = False
            self.assertEqual(list(self.session.keys()), ['x'])
            self.assertIs(self.session.accessed, True)
            self.assertIs(self.session.modified, False)

        def test_items(self):
            self.session['x'] = 1
            self.session.modified = False
            self.session.accessed = False
            self.assertEqual(list(self.session.items()), [('x', 1)])
            self.assertIs(self.session.accessed, True)
            self.assertIs(self.session.modified, False)

        def test_clear(self):
            self.session['x'] = 1
            self.session.modified = False
            self.session.accessed = False
            self.assertEqual(list(self.session.items()), [('x', 1)])
            self.session.clear()
            self.assertEqual(list(self.session.items()), [])
            self.assertIs(self.session.accessed, True)
            self.assertIs(self.session.modified, True)

        def test_save(self):
            self.session.save()
            self.assertIs(self.session.exists(self.session.session_key), True)

        def test_delete(self):
            self.session.save()
            self.session.delete(self.session.session_key)
            self.assertIs(self.session.exists(self.session.session_key), False)

        def test_flush(self):
            self.session['foo'] = 'bar'
            self.session.save()
            prev_key = self.session.session_key
            self.session.flush()
            self.assertIs(self.session.exists(prev_key), False)
            self.assertNotEqual(self.session.session_key, prev_key)
            self.assertIsNone(self.session.session_key)
            self.assertIs(self.session.modified, True)
            self.assertIs(self.session.accessed, True)

        def test_cycle(self):
            self.session['a'], self.session['b'] = 'c', 'd'
            self.session.save()
            prev_key = self.session.session_key
            prev_data = list(self.session.items())
            self.session.cycle_key()
            self.assertIs(self.session.exists(prev_key), False)
            self.assertNotEqual(self.session.session_key, prev_key)
            self.assertEqual(list(self.session.items()), prev_data)

        def test_cycle_with_no_session_cache(self):
            self.session['a'], self.session['b'] = 'c', 'd'
            self.session.save()
            prev_data = self.session.items()
            self.session = self.backend(self.session.session_key)
            self.assertIs(hasattr(self.session, '_session_cache'), False)
            self.session.cycle_key()
            self.assertCountEqual(self.session.items(), prev_data)

        def test_save_doesnt_clear_data(self):
            self.session['a'] = 'b'
            self.session.save()
            self.assertEqual(self.session['a'], 'b')

        def test_invalid_key(self):
            # Submitting an invalid session key (either by guessing, or if the db has
            # removed the key) results in a new key being generated.
            try:
                session = self.backend('1')
                session.save()
                self.assertNotEqual(session.session_key, '1')
                self.assertIsNone(session.get('cat'))
                session.delete()
            finally:
                # Some backends leave a stale cache entry for the invalid
                # session key; make sure that entry is manually deleted
                session.delete('1')

        def test_session_key_empty_string_invalid(self):
            """Falsey values (Such as an empty string) are rejected."""
            self.session._session_key = ''
            self.assertIsNone(self.session.session_key)

        def test_session_key_too_short_invalid(self):
            """Strings shorter than 8 characters are rejected."""
            self.session._session_key = '1234567'
            self.assertIsNone(self.session.session_key)

        def test_session_key_valid_string_saved(self):
            """Strings of length 8 and up are accepted and stored."""
            self.session._session_key = '12345678'
            self.assertEqual(self.session.session_key, '12345678')

        def test_session_key_is_read_only(self):
            def set_session_key(session):
                session.session_key = session._get_new_session_key()
            with self.assertRaises(AttributeError):
                set_session_key(self.session)

        # Custom session expiry
        def test_default_expiry(self):
            # A normal session has a max age equal to settings
            self.assertEqual(self.session.get_expiry_age(), SESSION_COOKIE_AGE)

            # So does a custom session with an idle expiration time of 0 (but it'll
            # expire at browser close)
            self.session.set_expiry(0)
            self.assertEqual(self.session.get_expiry_age(), SESSION_COOKIE_AGE)

        def test_custom_expiry_seconds(self):
            modification = datetime.now()

            self.session.set_expiry(10)

            date = self.session.get_expiry_date(modification=modification)
            self.assertEqual(date, modification + timedelta(seconds=10))

            age = self.session.get_expiry_age(modification=modification)
            self.assertEqual(age, 10)

        def test_custom_expiry_timedelta(self):
            modification = datetime.now()
            with freeze_time(modification):
                self.session.set_expiry(timedelta(seconds=10))

                date = self.session.get_expiry_date(modification=modification)
                self.assertEqual(date, modification + timedelta(seconds=10))

                age = self.session.get_expiry_age(modification=modification)
                self.assertEqual(age, 10)

        def test_custom_expiry_datetime(self):
            modification = datetime.now()

            self.session.set_expiry(modification + timedelta(seconds=10))

            date = self.session.get_expiry_date(modification=modification)
            self.assertEqual(date, modification + timedelta(seconds=10))

            age = self.session.get_expiry_age(modification=modification)
            self.assertEqual(age, 10)

        def test_custom_expiry_reset(self):
            self.session.set_expiry(None)
            self.session.set_expiry(10)
            self.session.set_expiry(None)
            self.assertEqual(self.session.get_expiry_age(), SESSION_COOKIE_AGE)

        def test_decode(self):
            # Ensure we can decode what we encode
            data = {'a test key': 'a test value'}
            encoded = self.session.encode(data)
            self.assertEqual(self.session.decode(encoded), data)

        def test_cycle_data(self):
            session_id = str(uuid.uuid4())
            session = self.backend(session_id)
            session['name'] = 'test_cycle_data'
            session['session_id'] = session_id
            session.save()

            # before cycling data
            # check data has been saved
            self.assertEqual(session.items(),
                              self.backend(session_id).items())

            # saving items before they are cleared
            pre_session_items = session.items()

            new_session_id = session.cycle_data()

            # check a new session id was generated
            self.assertNotEqual(session_id, new_session_id)

            new_session = self.backend(new_session_id)
            # sanity check
            self.assertEqual(new_session['session_id'], session_id)
            # check data is the same
            self.assertEqual(new_session.items(), pre_session_items)

            # check that data has been removed in the previous version
            previous_session = self.backend(session_id)
            del previous_session['_session_expiry']
            self.assertEqual(list(previous_session.items()), [])


class TestWithFileObject(SessionTest.SessionTestsMixin):

    def backend(self, session_key=None):
        return SessionStore(session_key, FilesystemStore("./session_data_test"))
