"""Phase 6 hardening: the startup refusal for a guessable JWT secret, emails in one
(lower-case) form, a limit on failed sign-ins, and a configurable CORS list."""

import logging

import pytest
from fastapi.testclient import TestClient

from app import config, models
from app.main import app, check_secret_or_refuse, create_app
from app.security import insecure_secret_problem, normalize_email
from app.services.login_limiter import MAX_TRACKED_KEYS, LoginRateLimiter, limiter

GOOD_SECRET = "x" * 48


def register(client, email="alice@example.com", password="correct-horse"):
    return client.post("/auth/register", json={"email": email, "password": password})


def login(client, email="alice@example.com", password="correct-horse"):
    return client.post("/auth/login", data={"username": email, "password": password})


@pytest.fixture()
def raw():
    return TestClient(app)


# --- the JWT secret ---------------------------------------------------------------------------------


def test_the_built_in_default_is_a_problem():
    assert "built-in default" in insecure_secret_problem(config.DEFAULT_JWT_SECRET)


def test_a_short_secret_is_a_problem():
    assert "shorter than 32" in insecure_secret_problem("short-secret")
    assert insecure_secret_problem("x" * 31) is not None


def test_a_long_secret_is_fine():
    assert insecure_secret_problem("x" * 32) is None
    assert insecure_secret_problem(GOOD_SECRET) is None


def test_the_check_refuses_a_bad_secret_and_says_how_to_fix_it():
    with pytest.raises(RuntimeError) as info:
        check_secret_or_refuse(config.DEFAULT_JWT_SECRET, dev=False)
    message = str(info.value)
    assert "Refusing to start" in message and "JWT_SECRET_KEY" in message
    assert "secrets.token_urlsafe" in message and "NUCERA_DEV=true" in message


def test_the_check_passes_a_good_secret_without_the_dev_flag():
    check_secret_or_refuse(GOOD_SECRET, dev=False)  # no exception


def test_the_dev_flag_downgrades_the_refusal_to_a_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        check_secret_or_refuse(config.DEFAULT_JWT_SECRET, dev=True)
    assert "NUCERA_DEV" in caplog.text and "built-in default" in caplog.text


def test_the_check_reads_the_live_settings_by_default(monkeypatch):
    monkeypatch.setattr(config, "JWT_SECRET_KEY", config.DEFAULT_JWT_SECRET)
    monkeypatch.setattr(config, "NUCERA_DEV", False)
    with pytest.raises(RuntimeError):
        check_secret_or_refuse()
    monkeypatch.setattr(config, "JWT_SECRET_KEY", GOOD_SECRET)
    check_secret_or_refuse()


def test_the_server_itself_refuses_to_start_with_the_default_secret(monkeypatch):
    monkeypatch.setattr(config, "JWT_SECRET_KEY", config.DEFAULT_JWT_SECRET)
    monkeypatch.setattr(config, "NUCERA_DEV", False)
    with pytest.raises(RuntimeError, match="Refusing to start"):
        with TestClient(create_app()):  # entering the context runs the startup hook
            pass


def test_the_server_starts_with_a_real_secret_or_the_dev_flag(monkeypatch):
    monkeypatch.setattr(config, "JWT_SECRET_KEY", GOOD_SECRET)
    monkeypatch.setattr(config, "NUCERA_DEV", False)
    with TestClient(create_app()) as client:
        assert client.get("/health").json() == {"status": "healthy"}
    monkeypatch.setattr(config, "JWT_SECRET_KEY", config.DEFAULT_JWT_SECRET)
    monkeypatch.setattr(config, "NUCERA_DEV", True)
    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200


@pytest.mark.parametrize(
    "value,expected",
    [("true", True), ("1", True), ("YES", True), ("on", True), ("false", False), ("0", False), ("", False), ("nope", False)],
)
def test_the_dev_flag_is_read_from_the_environment(value, expected):
    """Loads the real config in a fresh process, since it is read once at import."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    backend = Path(__file__).resolve().parent.parent
    env = {**os.environ, "NUCERA_DEV": value}
    out = subprocess.run(
        [sys.executable, "-c", "import app.config as c; print(c.NUCERA_DEV)"],
        cwd=backend, env=env, capture_output=True, text=True,
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == str(expected)


def test_the_flag_defaults_to_off_so_a_fresh_install_must_set_a_secret():
    import os
    import subprocess
    import sys
    from pathlib import Path

    backend = Path(__file__).resolve().parent.parent
    env = {k: v for k, v in os.environ.items() if k not in ("NUCERA_DEV", "JWT_SECRET_KEY")}
    out = subprocess.run(
        [sys.executable, "-c", "import app.config as c; print(c.NUCERA_DEV, c.JWT_SECRET_KEY == c.DEFAULT_JWT_SECRET)"],
        cwd=backend, env=env, capture_output=True, text=True,
    )
    assert out.stdout.strip() == "False True"


# --- emails ----------------------------------------------------------------------------------------


def test_normalize_email_trims_and_lower_cases():
    assert normalize_email("  Alice@Example.COM ") == "alice@example.com"
    assert normalize_email("already@lower.com") == "already@lower.com"


def test_registering_stores_and_returns_the_lower_case_form(raw):
    body = register(raw, "Alice@Example.COM").json()
    assert body["email"] == "alice@example.com"


def test_an_address_in_another_case_is_the_same_account(raw):
    assert register(raw, "alice@example.com").status_code == 200
    dupe = register(raw, "ALICE@example.com")
    assert dupe.status_code == 400 and "already exists" in dupe.json()["detail"]


def test_signing_in_works_whatever_the_capitalisation(raw):
    register(raw, "Alice@Example.com")
    for typed in ("alice@example.com", "ALICE@EXAMPLE.COM", "Alice@Example.com", "  alice@example.com "):
        assert login(raw, typed).status_code == 200, typed


def test_a_wrong_password_is_still_a_401_in_any_case(raw):
    register(raw, "alice@example.com")
    assert login(raw, "ALICE@example.com", "wrong-password").status_code == 401


def test_an_account_stored_with_capitals_before_this_change_can_still_sign_in(raw, db_session):
    from app.security import hash_password

    db_session.add(models.User(email="Legacy@Example.com", hashed_password=hash_password("old-password")))
    db_session.commit()
    assert login(raw, "legacy@example.com", "old-password").status_code == 200
    assert login(raw, "LEGACY@EXAMPLE.COM", "old-password").status_code == 200
    # ...and registering the same address in lower case is refused rather than making a twin.
    assert register(raw, "legacy@example.com").status_code == 400


def test_the_token_works_for_the_same_account_whatever_case_was_typed(raw):
    register(raw, "Alice@Example.com")
    token = login(raw, "ALICE@example.com").json()["access_token"]
    me = raw.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["email"] == "alice@example.com"


def test_the_database_refuses_a_twin_account_even_if_the_app_were_bypassed(db_session):
    from sqlalchemy.exc import IntegrityError

    db_session.add(models.User(email="twin@example.com", hashed_password="x"))
    db_session.commit()
    db_session.add(models.User(email="TWIN@example.com", hashed_password="x"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# --- the limiter itself -------------------------------------------------------------------------------


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def make_limiter(max_failures=3, window=60, ip_max=10):
    clock = Clock()
    return LoginRateLimiter(max_failures, window, ip_max, clock), clock


def test_a_fresh_limiter_lets_everyone_try():
    lim, _ = make_limiter()
    assert lim.check("1.1.1.1", "a@x.com") == 0


def test_failures_below_the_limit_do_not_block():
    lim, _ = make_limiter(max_failures=3)
    lim.record_failure("1.1.1.1", "a@x.com")
    lim.record_failure("1.1.1.1", "a@x.com")
    assert lim.check("1.1.1.1", "a@x.com") == 0


def test_reaching_the_limit_blocks_until_the_oldest_failure_leaves_the_window():
    lim, clock = make_limiter(max_failures=3, window=60)
    for _ in range(3):
        lim.record_failure("1.1.1.1", "a@x.com")
        clock.advance(1)
    # Failures at t=0, 1, 2 (now t=3): the oldest expires at t=60, so 57 seconds from now.
    assert lim.check("1.1.1.1", "a@x.com") == 57
    clock.advance(56)
    assert lim.check("1.1.1.1", "a@x.com") == 1
    clock.advance(1)  # t=60: the first failure is out of the window; two remain, under the limit
    assert lim.check("1.1.1.1", "a@x.com") == 0


def test_the_wait_is_never_reported_as_zero_while_blocked():
    lim, clock = make_limiter(max_failures=1, window=60)
    lim.record_failure("ip", "e")
    clock.advance(59.6)
    assert lim.check("ip", "e") >= 1


def test_another_email_or_another_address_is_not_affected():
    lim, _ = make_limiter(max_failures=2)
    for _ in range(2):
        lim.record_failure("1.1.1.1", "a@x.com")
    assert lim.check("1.1.1.1", "a@x.com") > 0
    assert lim.check("1.1.1.1", "b@x.com") == 0  # same address, another email
    assert lim.check("2.2.2.2", "a@x.com") == 0  # another address cannot be locked out by strangers


def test_a_successful_sign_in_forgets_that_emails_failures_from_that_address():
    lim, _ = make_limiter(max_failures=3)
    lim.record_failure("ip", "a@x.com")
    lim.record_failure("ip", "a@x.com")
    lim.record_success("ip", "a@x.com")
    lim.record_failure("ip", "a@x.com")
    lim.record_failure("ip", "a@x.com")
    assert lim.check("ip", "a@x.com") == 0  # two failures since, not four


def test_one_address_trying_many_emails_hits_the_looser_per_address_cap():
    lim, _ = make_limiter(max_failures=3, ip_max=5)
    for i in range(5):
        lim.record_failure("9.9.9.9", f"user{i}@x.com")  # never more than once per email
    assert lim.check("9.9.9.9", "user0@x.com") > 0
    assert lim.check("9.9.9.9", "brand-new@x.com") > 0  # every email from that address
    assert lim.check("8.8.8.8", "user0@x.com") == 0


def test_the_per_address_cap_survives_a_success_for_one_email():
    lim, _ = make_limiter(max_failures=3, ip_max=3)
    for i in range(3):
        lim.record_failure("ip", f"u{i}@x.com")
    lim.record_success("ip", "u0@x.com")
    assert lim.check("ip", "u1@x.com") > 0  # a lucky success doesn't wash the address clean


def test_memory_is_bounded(monkeypatch):
    import app.services.login_limiter as module

    monkeypatch.setattr(module, "MAX_TRACKED_KEYS", 5)
    lim, _ = make_limiter()
    for i in range(50):
        lim.record_failure("ip", f"user{i}@x.com")
    assert len(lim._by_pair) <= 5
    assert MAX_TRACKED_KEYS == 10_000  # the real bound is a sane size


def test_reset_clears_everything():
    lim, _ = make_limiter(max_failures=1)
    lim.record_failure("ip", "e")
    lim.reset()
    assert lim.check("ip", "e") == 0


# --- the limit on the sign-in route -------------------------------------------------------------------------


def fail(client, n, email="alice@example.com"):
    return [login(client, email, "wrong-password").status_code for _ in range(n)]


def test_too_many_wrong_passwords_lock_that_email_out_with_a_retry_after(raw):
    register(raw)
    assert fail(raw, config.LOGIN_MAX_FAILURES) == [401] * config.LOGIN_MAX_FAILURES
    blocked = login(raw)  # even the right password is refused now
    assert blocked.status_code == 429
    assert "Too many failed sign-in attempts. Try again in" in blocked.json()["detail"]
    assert 1 <= int(blocked.headers["Retry-After"]) <= config.LOGIN_WINDOW_SECONDS


def test_the_lock_out_ends_when_the_window_has_passed(raw, monkeypatch):
    register(raw)
    fail(raw, config.LOGIN_MAX_FAILURES)
    assert login(raw).status_code == 429
    clock = Clock()
    clock.now = limiter._clock() + config.LOGIN_WINDOW_SECONDS + 1
    monkeypatch.setattr(limiter, "_clock", clock)
    assert login(raw).status_code == 200


def test_an_email_that_does_not_exist_is_limited_the_same_way(raw):
    statuses = fail(raw, config.LOGIN_MAX_FAILURES + 1, email="nobody@example.com")
    assert statuses[:-1] == [401] * config.LOGIN_MAX_FAILURES and statuses[-1] == 429


def test_the_limit_does_not_reveal_whether_an_account_exists(raw):
    register(raw, "real@example.com")
    fail(raw, config.LOGIN_MAX_FAILURES, "real@example.com")
    fail(raw, config.LOGIN_MAX_FAILURES, "ghost@example.com")
    real = login(raw, "real@example.com")
    ghost = login(raw, "ghost@example.com")
    assert real.status_code == ghost.status_code == 429
    assert real.json()["detail"].split(" in ")[0] == ghost.json()["detail"].split(" in ")[0]


def test_a_successful_login_resets_the_count(raw):
    register(raw)
    fail(raw, config.LOGIN_MAX_FAILURES - 1)
    assert login(raw).status_code == 200
    assert fail(raw, config.LOGIN_MAX_FAILURES - 1) == [401] * (config.LOGIN_MAX_FAILURES - 1)  # not locked


def test_locking_out_one_email_does_not_affect_another_account(raw):
    register(raw, "alice@example.com")
    register(raw, "bob@example.com")
    fail(raw, config.LOGIN_MAX_FAILURES, "alice@example.com")
    assert login(raw, "alice@example.com").status_code == 429
    assert login(raw, "bob@example.com").status_code == 200


def test_capitalisation_does_not_dodge_the_limit(raw):
    register(raw)
    for i in range(config.LOGIN_MAX_FAILURES):
        login(raw, "ALICE@EXAMPLE.COM" if i % 2 else "alice@example.com", "wrong-password")
    assert login(raw, "Alice@Example.com").status_code == 429


def test_registering_and_using_a_token_are_not_limited_by_failed_logins(raw):
    register(raw)
    token = login(raw).json()["access_token"]
    fail(raw, config.LOGIN_MAX_FAILURES)
    assert raw.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert register(raw, "carol@example.com").status_code == 200


# --- CORS ----------------------------------------------------------------------------------------------------------


def test_origins_are_split_trimmed_and_de_duplicated():
    assert config.parse_origins(" http://a.test , http://b.test/ ,,http://a.test") == ["http://a.test", "http://b.test"]
    assert config.parse_origins("") == []


@pytest.mark.parametrize("raw_value", ["*", "http://a.test,*", " * "])
def test_a_wildcard_origin_is_refused(raw_value):
    with pytest.raises(ValueError, match="may not contain"):
        config.parse_origins(raw_value)


def test_the_defaults_are_the_two_local_dev_origins():
    assert config.parse_origins("http://localhost:3000,http://localhost:3002") == ["http://localhost:3000", "http://localhost:3002"]
    assert "http://localhost:3000" in config.CORS_ORIGINS


def preflight(origins, origin):
    client = TestClient(create_app(origins))
    return client.options(
        "/auth/login",
        headers={"Origin": origin, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"},
    )


def test_a_listed_origin_is_allowed_with_credentials():
    resp = preflight(["https://nucera.example"], "https://nucera.example")
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "https://nucera.example"
    assert resp.headers["access-control-allow-credentials"] == "true"


def test_an_unlisted_origin_is_not():
    resp = preflight(["https://nucera.example"], "https://evil.example")
    assert "access-control-allow-origin" not in resp.headers


def test_the_app_uses_the_configured_origins_by_default(monkeypatch):
    monkeypatch.setattr(config, "CORS_ORIGINS", ["https://configured.example"])
    client = TestClient(create_app())
    ok = client.options("/auth/login", headers={"Origin": "https://configured.example", "Access-Control-Request-Method": "POST"})
    assert ok.headers.get("access-control-allow-origin") == "https://configured.example"
    other = client.options("/auth/login", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in other.headers  # the old hard-coded list is gone
