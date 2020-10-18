from copy import deepcopy

import pytest

from ussd.core import UssdEngine
from ussd.store.journey_store import DummyStore, DynamoDb, YamlJourneyStore
from unittest import TestCase
from marshmallow.exceptions import ValidationError


class TestDriverStore:

    class BaseDriverStoreTestCase(TestCase):
        __test__ = False
        maxDiff = None

        def setUp(self):
            # setup driver instance
            self.driver = self.setup_driver()

        def tearDown(self):
            self.driver.flush()

        @staticmethod
        def setup_driver():
            pass

        def test_creating_invalid_journey(self):
            sample_journey = {
                "initial_screen": {
                    "type": "initial_screen",
                    "next_screen": "end_screen",
                    "default_language": "en"
                },
            }

            self.assertRaises(ValidationError,
                              self.driver.save,
                              name="journey_a",
                              journey=sample_journey,
                              version="0.0.2")

        def test_creating_journey(self):
            sample_journey = {
                "initial_screen": {
                    "type": "initial_screen",
                    "next_screen": "end_screen",
                    "default_language": "en"
                },
                "end_screen": {
                    "type": "quit_screen",
                    "text": "end screen"
                }
            }

            # Creating journey_a
            sample_journey_one = deepcopy(sample_journey)

            sample_journey_two = deepcopy(sample_journey_one)
            sample_journey_two['end_screen']['text'] = "end screen of sample journey two"

            sample_journey_three = deepcopy(sample_journey)
            sample_journey_three['end_screen']['text'] = "end screen of sample journey three"

            self.driver.save(name="journey_a", journey=sample_journey_one, version="0.0.1")
            self.driver.save(name="journey_a", journey=sample_journey_two, version="0.0.2")
            self.driver.save(name="journey_a", journey=sample_journey_three, version="0.0.3")

            # Creating journey_b
            sample_journey_b_one = deepcopy(sample_journey)
            sample_journey_b_one['end_screen']['text'] = "end screen of sample journey_b one"

            sample_journey_b_two = deepcopy(sample_journey_b_one)
            sample_journey_b_two['end_screen']['text'] = "end screen of sample journey_b two"

            sample_journey_b_three = deepcopy(sample_journey_b_one)
            sample_journey_b_three['end_screen']['text'] = "end screen of sample journey_b three"

            self.driver.save(name="journey_b", journey=sample_journey_b_one, version="0.0.1")
            self.driver.save(name="journey_b", journey=sample_journey_b_two, version="0.0.2")
            self.driver.save(name="journey_b", journey=sample_journey_b_three, version="0.0.3")

            # test getting the journey a
            a = sample_journey_two
            b = self.driver.get('journey_a', '0.0.2')
            self.assertDictEqual(sample_journey_two, self.driver.get('journey_a', '0.0.2'))
            self.assertEqual(sample_journey_three, self.driver.get('journey_a', '0.0.3'))
            self.assertEqual(sample_journey_one, self.driver.get('journey_a', '0.0.1'))

            # test getting the journey b
            self.assertEqual(sample_journey_b_two, self.driver.get('journey_b', '0.0.2'))
            self.assertEqual(sample_journey_b_three, self.driver.get('journey_b', '0.0.3'))
            self.assertEqual(sample_journey_b_one, self.driver.get('journey_b', '0.0.1'))

            # test that you cannot save/update with the same version
            self.assertRaises(ValidationError, self.driver.save, name="journey_a",
                              journey=sample_journey_two, version="0.0.3")

            # test getting all the journeys
            self.assertDictEqual(
                {"0.0.1": sample_journey_one, "0.0.2": sample_journey_two, "0.0.3": sample_journey_three},
                self.driver.get_all_journey_version('journey_a'))

            # test getting the latest journey
            self.assertEqual(sample_journey_three, self.driver.get('journey_a'))

            # test getting part of screen alone
            self.assertEqual(sample_journey_three['end_screen'],
                             self.driver.get('journey_a', screen_name='end_screen'))
            self.assertEqual(sample_journey_two['end_screen'],
                             self.driver.get('journey_a', version="0.0.2", screen_name='end_screen'))

            # sanity check
            assert sample_journey_two['end_screen'] != sample_journey['end_screen']

            # testing deleting
            self.driver.delete('journey_a', version="0.0.1")
            self.assertIsNone(self.driver.get('journey_a', version="0.0.1", propagate_error=False))

            # test getting journey that doesn't exists throws an error
            self.assertRaises(ValidationError, self.driver.get, 'journey_a', version="0.0.1")

            # check that it hasn't deleted anything
            self.assertEqual(len(self.driver.get_all_journey_version('journey_a')), 2)

            # deleting all journeys including the versions
            self.driver.delete('journey_a')
            self.assertEqual(len(self.driver.get_all_journey_version('journey_a')), 0)

        def test_saving_journeys_thats_still_in_edit_mode(self):
            sample_journey = {
                "initial_screen": {
                    "type": "initial_screen",
                    "next_screen": "end_screen",
                    "default_language": "en"
                },
                "end_screen": {
                    "type": "quit_screen",
                    "text": "end screen"
                }
            }

            self.driver.save(name="journey_a", journey=sample_journey, version="0.0.1")

            self.assertEqual(sample_journey, self.driver.get('journey_a', '0.0.1'))

            sample_journey_edit_mode = {
                "initial_screen": {
                    "type": "initial_screen",
                    "next_screen": "end_screen",
                    "default_language": "en"
                },
            }

            # confirm its invalid
            is_valid, errors = UssdEngine.validate_ussd_journey(sample_journey_edit_mode)
            self.assertFalse(is_valid)

            # but we can still save it under edit mode
            self.driver.save(name='journey_a', journey=sample_journey_edit_mode, edit_mode=True)

            # stills get the valid one that was saved.
            self.assertEqual(sample_journey, self.driver.get('journey_a'))

            # getting the one use edit mode
            self.assertEqual(sample_journey_edit_mode, self.driver.get('journey_a', edit_mode=True))

            sample_journey_edit_mode['invalid_screen'] = "invalid_screen"

            # and we can still save it again
            self.driver.save(name='journey_a', journey=sample_journey_edit_mode, edit_mode=True)
            self.assertEqual(sample_journey_edit_mode, self.driver.get('journey_a', edit_mode=True))

        def test_crud_for_multiple_users(self):
            driver_with_user_1 = self.setup_driver(user="user_1")

            driver_with_user_2 = self.setup_driver(user="user_2")

            user_1 = {
                "journey_a": {
                    "0.0.1": {
                        "initial_screen": {
                            "type": "initial_screen",
                            "next_screen": "end_screen",
                            "default_language": "en"
                        },
                        "end_screen": {
                            "type": "quit_screen",
                            "text": "end screen for user 1 journey a 1"
                        }
                    },
                    "0.0.2": {
                        "initial_screen": {
                            "type": "initial_screen",
                            "next_screen": "end_screen",
                            "default_language": "en"
                        },
                        "end_screen": {
                            "type": "quit_screen",
                            "text": "end screen for user 1 journey a version 1"
                        }
                    }
                },
                "journey_b": {
                    "0.0.1": {
                        "initial_screen": {
                            "type": "initial_screen",
                            "next_screen": "end_screen",
                            "default_language": "en"
                        },
                        "end_screen": {
                            "type": "quit_screen",
                            "text": "end screen for user 1 journey b version 1"
                        }
                    }
                }
            }

            # create journey for user one
            driver_with_user_1.save(name="journey_a", version="0.0.1",
                                    journey=user_1["journey_a"]["0.0.1"])

            # sanity check journey was created
            self.assertEqual(
                driver_with_user_1.get("journey_a", version="0.0.1"),
                user_1["journey_a"]["0.0.1"])

            # check second driver can't access the journey with different user
            self.assertRaises(ValidationError, driver_with_user_2.get, "journey_a", version="0.0.1")

            # create another journey with a different version
            driver_with_user_1.save(name="journey_a", version="0.0.2",
                                    journey=user_1["journey_a"]["0.0.2"])

            # create another journey
            driver_with_user_1.save(name="journey_b", version="0.0.1",
                                    journey=user_1["journey_b"]["0.0.1"])

            # test getting all the journeys
            self.assertDictEqual(
                user_1["journey_a"],
                driver_with_user_1.get_all_journey_version('journey_a'))

            # test getting all the journeys returns for user one only
            self.assertDictEqual(
                user_1,
                driver_with_user_1.all())

            # now create journey for user 2
            user_2 = {
                "journey_a": {
                    "0.0.1": {
                        "initial_screen": {
                            "type": "initial_screen",
                            "next_screen": "end_screen",
                            "default_language": "en"
                        },
                        "end_screen": {
                            "type": "quit_screen",
                            "text": "end screen for user 2 journey a 1"
                        }
                    }
                },
                "journey_user_2": {
                    "0.0.1": {
                        "initial_screen": {
                            "type": "initial_screen",
                            "next_screen": "end_screen",
                            "default_language": "en"
                        },
                        "end_screen": {
                            "type": "quit_screen",
                            "text": "end screen for user 2 journey a 1"
                        }
                    }
                }
            }

            driver_with_user_2.save(name="journey_a", version="0.0.1",
                                    journey=user_2["journey_a"]['0.0.1'])

            self.assertEqual(
                driver_with_user_2.get("journey_a", version="0.0.1"),
                user_2["journey_a"]["0.0.1"]
            )

            # create the other journey
            driver_with_user_2.save(name="journey_user_2", version="0.0.1",
                                    journey=user_2["journey_user_2"]['0.0.1'])

            # check journey_a for user one is not equal as journey for user 2
            self.assertNotEqual(
                driver_with_user_1.get("journey_a", version="0.0.1"),
                driver_with_user_2.get("journey_a", version="0.0.1"),
            )

            # test getting all the journeys
            self.assertDictEqual(
                user_2["journey_a"],
                driver_with_user_2.get_all_journey_version('journey_a'))

            # test getting all the journeys returns for user one only
            self.assertDictEqual(
                user_2,
                driver_with_user_2.all())


class TestDummyStore(TestDriverStore.BaseDriverStoreTestCase):
    __test__ = True

    @staticmethod
    def setup_driver(user="default") -> DummyStore:
        return DummyStore.DummyStore(user=user)


class TestYamlJourneyStore(TestDriverStore.BaseDriverStoreTestCase):
    __test__ = True

    @staticmethod
    def setup_driver(user="default") -> YamlJourneyStore:
        return YamlJourneyStore.YamlJourneyStore(user=user)
