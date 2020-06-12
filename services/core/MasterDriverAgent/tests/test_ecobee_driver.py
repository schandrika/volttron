import copy
import datetime
import requests
from requests.exceptions import HTTPError
import pytest

from services.core.MasterDriverAgent.master_driver.interfaces import ecobee
from volttron.platform.agent import utils

VALID_ECOBEE_CONFIG = {
    "API_KEY": "TEST_KEY",
    "DEVICE_ID": 8675309,
}

VALID_ECOBEE_REGISTRY = [
    {
        "Point Name": "hold1",
        "Volttron Point Name": "testHold",
        "Units": "%",
        "Type": "hold",
        "Writable": "True",
        "Readable": "True"
    }, {
        "Point Name": "setting1",
        "Volttron Point Name": "testSetting",
        "Units": "degC",
        "Type": "setting",
        "Writable": "False",
        "Readable": "True"
    }, {
        "Point Name": "testNoRead",
        "Volttron Point Name": "testNoRead",
        "Units": "degC",
        "Type": "setting",
        "Writable": "True",
        "Readable": "False"
    }
]

REMOTE_RESPONSE = {
    "thermostatList": [
        {
            "identifier": 8675309,
            "settings": {
                "setting1": 0,
                "setting2": 1
            },
            "runtime": {
                "hold1": 0,
                "hold2": 1
            },
            "events": [
                {"test1": "test1", "type": "program"},
                {"test2": "test2", "type": "vacation"}
            ],
            "equipmentStatus": "testEquip1,testEquip3"
        }
    ]
}


class MockEcobee(ecobee.Interface):

    def __init__(self):
        super(MockEcobee, self).__init__()
        self.auth_config_stored = False
        self.authorization_code = False
        self.access_token = False
        self.refresh_token = False
        self.refresh_state = False
        self.poll_greenlet_thermostats = "test"

    def get_auth_config_from_store(self):
        if not self.auth_config_stored:
            return None
        else:
            return {
                "AUTH_CODE": self.authorization_code,
                "ACCESS_TOKEN": self.access_token,
                "REFRESH_TOKEN": self.refresh_token
            }

    def update_auth_config(self):
        self.auth_config_stored = True

    def authorize_application(self):
        self.authorization_code = True
        self.authorization_stage = "REQUEST_TOKENS"

    def request_tokens(self):
        if self.authorization_code:
            self.refresh_token = True
            self.access_token = True
            self.authorization_stage = "AUTHORIZED"
        else:
            raise requests.exceptions.HTTPError("Not authorized to request tokens")

    def refresh_tokens(self):
        if self.refresh_token:
            self.refresh_token = True
            self.access_token = True
            self.authorization_stage = "AUTHORIZED"
        else:
            raise requests.exceptions.HTTPError("Not authorized to refresh tokens")

    def get_data_remote(self, request_type, url, **kwargs):
        if self.authorization_stage != "AUTHORIZED" or not self.access_token:
            self.update_authorization()
        if self.authorization_stage == "AUTHORIZED" and self.access_token:
            return REMOTE_RESPONSE
        else:
            raise HTTPError("Failed to get remote Ecobee data")


@pytest.fixture()
def mock_ecobee():
    return MockEcobee()


def test_request_tokens(mock_ecobee):
    # should set request token and access token to true
    mock_ecobee.authorization_code = True
    mock_ecobee.refresh_token = False
    mock_ecobee.access_token = False
    mock_ecobee.authorization_stage = "REQUEST_TOKENS"
    # make sure this fails with the correct failure mode
    mock_ecobee.update_authorization()
    assert mock_ecobee.authorization_code is True
    assert mock_ecobee.refresh_token is True
    assert mock_ecobee.access_token is True


def test_request_tokens_bad_auth_code(mock_ecobee):
    # should only fail if auth code is bad
    mock_ecobee.authorization_code = False
    mock_ecobee.refresh_token = False
    mock_ecobee.access_token = False
    mock_ecobee.authorization_stage = "REQUEST_TOKENS"
    # make sure this fails with the correct failure mode
    with pytest.raises(requests.exceptions.HTTPError, match=r'Not authorized to request tokens'):
        mock_ecobee.update_authorization()
    assert mock_ecobee.authorization_code is False
    assert mock_ecobee.refresh_token is False
    assert mock_ecobee.access_token is False


def test_refresh_tokens(mock_ecobee):
    # should set request token and access token to true
    mock_ecobee.authorization_code = True
    mock_ecobee.refresh_token = True
    mock_ecobee.access_token = False
    mock_ecobee.authorization_stage = "REFRESH_TOKENS"
    # make sure the code token is set properly
    mock_ecobee.update_authorization()
    assert mock_ecobee.authorization_code is True
    assert mock_ecobee.refresh_token is True
    assert mock_ecobee.access_token is True


def test_refresh_tokens_bad_auth_code(mock_ecobee):
    # should still be able to refresh if the existing refresh token is valid even if the auth code is not
    mock_ecobee.authorization_code = False
    mock_ecobee.refresh_token = True
    mock_ecobee.access_token = False
    mock_ecobee.authorization_stage = "REFRESH_TOKENS"
    # should still work as the only token that's needed for refresh is the refresh token
    mock_ecobee.update_authorization()
    assert mock_ecobee.authorization_code is False
    assert mock_ecobee.refresh_token is True
    assert mock_ecobee.access_token is True


def test_refresh_tokens_bad_refresh_token(mock_ecobee):
    mock_ecobee.authorization_code = True
    mock_ecobee.refresh_token = False
    mock_ecobee.access_token = False
    mock_ecobee.authorization_stage = "REFRESH_TOKENS"
    # make sure this fails with the correct failure mode
    with pytest.raises(requests.exceptions.HTTPError, match=r'Not authorized to refresh tokens'):
        mock_ecobee.update_authorization()
    assert mock_ecobee.authorization_code is True
    assert mock_ecobee.refresh_token is False
    assert mock_ecobee.access_token is False


def test_configure_ecobee_success(mock_ecobee):
    mock_ecobee.configure(VALID_ECOBEE_CONFIG, VALID_ECOBEE_REGISTRY)
    assert mock_ecobee.authorization_code
    assert mock_ecobee.refresh_token
    assert mock_ecobee.access_token
    # Test configure from existing auth
    auth_config_path = ecobee.AUTH_CONFIG_PATH.format(VALID_ECOBEE_CONFIG.get("DEVICE_ID"))
    assert mock_ecobee.auth_config_path == auth_config_path
    assert mock_ecobee.authorization_stage == "AUTHORIZED"
    assert mock_ecobee.thermostat_data == REMOTE_RESPONSE
    registers = {register.point_name for register in
                 mock_ecobee.get_registers_by_type("byte", False) + mock_ecobee.get_registers_by_type("byte", True)}
    assert {"testNoRead", "testSetting", "testHold", "Programs", "Vacations", "Status"} == registers


def test_configure_ecobee_invalid_id(mock_ecobee):
    invalid_ecobee_config = copy.deepcopy(VALID_ECOBEE_CONFIG)
    invalid_ecobee_config["DEVICE_ID"] = "woops"
    with pytest.raises(ValueError, match=r"Ecobee driver requires Ecobee device identifier as int, got: .*"):
        mock_ecobee.configure(invalid_ecobee_config, VALID_ECOBEE_REGISTRY)


def test_configure_ecobee_invalid_registers(mock_ecobee):
    # Not having a "point_name" entry should cause no point to be added, but no error to be thrown
    # all other registers should still be built
    no_point_name = [{
        "Volttron Point Name": "testHold",
        "Units": "%",
        "Type": "hold",
        "Writable": "True",
        "Readable": "True"
    }, VALID_ECOBEE_REGISTRY[1]]
    mock_ecobee.configure(VALID_ECOBEE_CONFIG, no_point_name)
    assert mock_ecobee.thermostat_data == REMOTE_RESPONSE
    registers = {register.point_name for register in
                 mock_ecobee.get_registers_by_type("byte", False) + mock_ecobee.get_registers_by_type("byte", True)}
    assert {"testSetting", "Programs", "Vacations", "Status"} == registers

    # An unsupported type should cause no point to be added, but no error to be thrown
    # all other registers should still be built
    no_point_name = [{
        "Volttron Point Name": "testHold",
        "Units": "%",
        "Type": "test",
        "Writable": "True",
        "Readable": "True"
    }, VALID_ECOBEE_REGISTRY[1]]
    mock_ecobee.configure(VALID_ECOBEE_CONFIG, no_point_name)
    assert mock_ecobee.thermostat_data == REMOTE_RESPONSE
    registers = {register.point_name for register in
                 mock_ecobee.get_registers_by_type("byte", False) + mock_ecobee.get_registers_by_type("byte", True)}
    assert {"testSetting", "Programs", "Vacations", "Status"} == registers


def test_get_thermostat_data_success(mock_ecobee):
    mock_ecobee.configure(VALID_ECOBEE_CONFIG, VALID_ECOBEE_REGISTRY)
    assert mock_ecobee.thermostat_data == REMOTE_RESPONSE
    data_cache = mock_ecobee.cache.get('https://api.ecobee.com/1/thermostat')
    curr_timestamp = utils.parse_timestamp_string(data_cache.get("request_timestamp"))

    # Check that we get cached data when possible
    mock_ecobee.get_thermostat_data()
    assert mock_ecobee.thermostat_data == REMOTE_RESPONSE
    data_cache = mock_ecobee.cache.get('https://api.ecobee.com/1/thermostat')
    refresh_timestamp = utils.parse_timestamp_string(data_cache.get("request_timestamp"))
    assert refresh_timestamp == curr_timestamp

    # cause a request_tokens request to occur during get_ecobee_data
    mock_ecobee.authorization_code = True
    mock_ecobee.refresh_token = True
    mock_ecobee.access_token = True
    mock_ecobee.ecobee_data = None
    cleanup_mock_cache(mock_ecobee)
    mock_ecobee.get_thermostat_data()
    assert mock_ecobee.thermostat_data == REMOTE_RESPONSE
    data_cache = mock_ecobee.cache.get('https://api.ecobee.com/1/thermostat')
    refresh_timestamp = utils.parse_timestamp_string(data_cache.get("request_timestamp"))
    assert refresh_timestamp > curr_timestamp

    # should handle having to get a new refresh token and still fetch data
    mock_ecobee.access_token = False
    mock_ecobee.authorization_stage = "REFRESH_TOKENS"
    mock_ecobee.ecobee_data = None
    cleanup_mock_cache(mock_ecobee)
    mock_ecobee.get_thermostat_data()
    assert mock_ecobee.thermostat_data == REMOTE_RESPONSE
    assert mock_ecobee.access_token is True
    data_cache = mock_ecobee.cache.get('https://api.ecobee.com/1/thermostat')
    refresh_timestamp = utils.parse_timestamp_string(data_cache.get("request_timestamp"))
    assert refresh_timestamp > curr_timestamp

    # should handle having to get a new refresh token and still fetch data
    mock_ecobee.refresh_token = False
    mock_ecobee.access_token = False
    mock_ecobee.authorization_stage = "REQUEST_TOKENS"
    mock_ecobee.ecobee_data = None
    cleanup_mock_cache(mock_ecobee)
    mock_ecobee.get_thermostat_data()
    assert mock_ecobee.thermostat_data == REMOTE_RESPONSE
    assert mock_ecobee.access_token is True
    assert mock_ecobee.refresh_token is True

    # now should pull from cache again
    data_cache = mock_ecobee.cache.get('https://api.ecobee.com/1/thermostat')
    timestamp = data_cache.get("request_timestamp")
    mock_ecobee.get_thermostat_data()
    data_cache = mock_ecobee.cache.get('https://api.ecobee.com/1/thermostat')
    next_timestamp = data_cache.get("request_timestamp")
    assert timestamp == next_timestamp

def test_get_thermostat_data_no_auth(mock_ecobee):
    mock_ecobee.configure(VALID_ECOBEE_CONFIG, VALID_ECOBEE_REGISTRY)
    mock_ecobee.authorization_code = False
    mock_ecobee.refresh_token = False
    mock_ecobee.access_token = False
    mock_ecobee.ecobee_data = None
    cleanup_mock_cache(mock_ecobee)
    with pytest.raises(HTTPError, match=r""):
        mock_ecobee.get_thermostat_data()
    assert mock_ecobee.ecobee_data is None


def cleanup_mock_cache(mock_ecobee):
    pop_keys = list(mock_ecobee.cache.keys())
    for key in pop_keys:
        mock_ecobee.cache.pop(key)


@pytest.mark.parametrize("point_name,expected_value", [("testSetting", 0),
                                                       ("testHold", 0),
                                                       ("Programs", [{"test1": "test1", "type": "program"}]),
                                                       ("Vacations", [{"test2": "test2", "type": "vacation"}]),
                                                       ("Status", ["testEquip1", "testEquip3"])
                                                       ])
def test_ecobee_get_point_success(mock_ecobee, point_name, expected_value):
    mock_ecobee.configure(VALID_ECOBEE_CONFIG, VALID_ECOBEE_REGISTRY)
    assert mock_ecobee.get_point(point_name) == expected_value
    # Set the Ecobee data to None to try to force to the ValueError check which resets the Ecobee data
    mock_ecobee.thermostat_data = None
    assert mock_ecobee.get_point(point_name) == expected_value


def test_ecobee_empty_values(mock_ecobee):
    mock_ecobee.configure(VALID_ECOBEE_CONFIG, VALID_ECOBEE_REGISTRY)
    empty_response = copy.deepcopy(REMOTE_RESPONSE)
    empty_response["thermostatList"][0]["equipmentStatus"] = ""
    empty_response["thermostatList"][0]["events"] = []
    mock_ecobee.thermostat_data = empty_response

    assert mock_ecobee.get_point("Status") == []
    assert mock_ecobee.get_point("Vacations") == []
    assert mock_ecobee.get_point("Programs") == []


def test_ecobee_get_point_unreadable(mock_ecobee):
    mixed_readable_registry = [{
        "Point Name": "hold1",
        "Volttron Point Name": "testHold",
        "Units": "%",
        "Type": "hold",
        "Writable": "True",
        "Readable": "True"
    }, {
        "Point Name": "setting1",
        "Volttron Point Name": "testSetting",
        "Units": "degC",
        "Type": "setting",
        "Writable": "False",
        "Readable": "True"
    }, {
        "Point Name": "hold2",
        "Volttron Point Name": "testHoldNoRead",
        "Units": "%",
        "Type": "hold",
        "Writable": "True",
        "Readable": "False"
    }, {
        "Point Name": "setting2",
        "Volttron Point Name": "testSettingNoRead",
        "Units": "degC",
        "Type": "setting",
        "Writable": "False",
        "Readable": "False"
    }]
    mock_ecobee.configure(VALID_ECOBEE_CONFIG, mixed_readable_registry)
    assert mock_ecobee.get_point("testHold") == 0
    assert mock_ecobee.get_point("testSetting") == 0
    with pytest.raises(RuntimeError, match=r"Requested read of write-only point testHoldNoRead"):
        mock_ecobee.get_point("testHoldNoRead")
    with pytest.raises(RuntimeError, match=r"Requested read of write-only point testSettingNoRead"):
        mock_ecobee.get_point("testSettingNoRead")


@pytest.mark.parametrize("point_name,expected_value", [("testSetting", 0),
                                                       ("testHold", 0),
                                                       ("Programs", [{"test1": "test1", "type": "program"}]),
                                                       ("Vacations", [{"test2": "test2", "type": "vacation"}]),
                                                       ("Status", ["testEquip1", "testEquip3"])
                                                       ])
def test_get_point_malformed_data(mock_ecobee, point_name, expected_value):
    mock_ecobee.configure(VALID_ECOBEE_CONFIG, VALID_ECOBEE_REGISTRY)
    data_cache = mock_ecobee.cache.get('https://api.ecobee.com/1/thermostat')
    curr_timestamp = utils.parse_timestamp_string(data_cache.get("request_timestamp"))

    # Malformed data should cause ValueErrors, which then trigger the data to be refreshed
    mock_ecobee.thermostat_data = { }
    assert mock_ecobee.get_point(point_name) == expected_value
    data_cache = mock_ecobee.cache.get('https://api.ecobee.com/1/thermostat')
    refresh_timestamp = utils.parse_timestamp_string(data_cache.get("request_timestamp"))
    assert refresh_timestamp > curr_timestamp
    curr_timestamp = refresh_timestamp
    mock_ecobee.thermostat_data = {
        "thermostatsList": [{
            "identifier": 8675309,
        }]
    }
    assert mock_ecobee.get_point(point_name) == expected_value
    data_cache = mock_ecobee.cache.get('https://api.ecobee.com/1/thermostat')
    refresh_timestamp = utils.parse_timestamp_string(data_cache.get("request_timestamp"))
    assert refresh_timestamp > curr_timestamp
    curr_timestamp = refresh_timestamp
    mock_ecobee.thermostat_data = {
        "thermostatsList": [{
            "identifier": 8675309,
            "settings": {},
            "runtime": {},
            "events": [""]
        }]
    }
    assert mock_ecobee.get_point(point_name) == expected_value
    data_cache = mock_ecobee.cache.get('https://api.ecobee.com/1/thermostat')
    refresh_timestamp = utils.parse_timestamp_string(data_cache.get("request_timestamp"))
    assert refresh_timestamp > curr_timestamp


def test_scrape_all_success(mock_ecobee):
    mock_ecobee.configure(VALID_ECOBEE_CONFIG, VALID_ECOBEE_REGISTRY)
    all_scrape = mock_ecobee._scrape_all()
    result = {
        "testSetting": 0,
        "testHold": 0,
        "Status": ["testEquip1", "testEquip3"],
        "Vacations": [{"test2": "test2", "type": "vacation"}],
        "Programs": [{"test1": "test1", "type": "program"}]
    }
    assert result == all_scrape


def test_scrape_all_trigger_refresh(mock_ecobee):
    mock_ecobee.configure(VALID_ECOBEE_CONFIG, VALID_ECOBEE_REGISTRY)
    mock_ecobee.thermostat_data = None
    cleanup_mock_cache(mock_ecobee)
    all_scrape = mock_ecobee._scrape_all()
    result = {
        "testSetting": 0,
        "testHold": 0,
        "Status": ["testEquip1", "testEquip3"],
        "Vacations": [{"test2": "test2", "type": "vacation"}],
        "Programs": [{"test1": "test1", "type": "program"}]
    }
    assert result == all_scrape
