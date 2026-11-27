"""Settings for the company roles: the usernames are fixed, the passwords optional."""

import pytest

from config import Settings


def settings(**overrides) -> Settings:
    return Settings(**overrides)


def test_a_wrong_request_role_is_ignored_with_a_warning_and_never_trusted():
    """A stale .env must not take the API down, and must never make request writes run as the generator."""
    with pytest.warns(UserWarning, match="APP_DB_USERNAME"):
        s = settings(APP_DB_USERNAME="chattie_generator", APP_DB_PASSWORD="a", GENERATOR_DB_PASSWORD="g")
    assert s.APP_DB_USERNAME == "chattie_app"
    assert "user=chattie_app" in s.APP_DATABASE_CONNINFO and "chattie_generator" not in s.APP_DATABASE_CONNINFO


def test_a_wrong_generator_role_name_is_ignored_too():
    with pytest.warns(UserWarning, match="GENERATOR_DB_USERNAME"):
        s = settings(GENERATOR_DB_USERNAME="chattie_app", APP_DB_PASSWORD="a", GENERATOR_DB_PASSWORD="g")
    assert s.GENERATOR_DB_USERNAME == "chattie_generator"
    assert "user=chattie_generator" in s.GENERATOR_DATABASE_CONNINFO


def test_blank_usernames_fall_back_to_the_fixed_names_without_a_warning(recwarn):
    s = settings(APP_DB_USERNAME="", GENERATOR_DB_USERNAME="")
    assert (s.APP_DB_USERNAME, s.GENERATOR_DB_USERNAME) == ("chattie_app", "chattie_generator")
    assert not [w for w in recwarn if "DB_USERNAME" in str(w.message)]


def test_company_features_need_both_passwords():
    assert settings(APP_DB_PASSWORD="a", GENERATOR_DB_PASSWORD="g").company_roles_configured is True
    assert settings(APP_DB_PASSWORD="a", GENERATOR_DB_PASSWORD="").company_roles_configured is False
    assert settings(APP_DB_PASSWORD=None, GENERATOR_DB_PASSWORD="g").company_roles_configured is False


def test_connection_strings_use_the_matching_role():
    s = settings(APP_DB_PASSWORD="a", GENERATOR_DB_PASSWORD="g")
    assert "user=chattie_app" in s.APP_DATABASE_CONNINFO and "user=chattie_generator" in s.GENERATOR_DATABASE_CONNINFO
