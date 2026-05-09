import pytest

from app.utils.security import SQLSecurityError, validate_sql

ALLOWED = ["users", "orders", "products"]


def test_valid_select():
    validate_sql("SELECT * FROM users", ALLOWED)


def test_valid_select_with_where():
    validate_sql("SELECT id, name FROM users WHERE active = 1", ALLOWED)


def test_valid_cte():
    validate_sql("WITH active AS (SELECT id FROM users) SELECT * FROM active", ALLOWED)


def test_valid_join():
    validate_sql("SELECT u.id, o.total FROM users u JOIN orders o ON u.id = o.user_id", ALLOWED)


def test_valid_aggregate():
    validate_sql("SELECT COUNT(*) as cnt, AVG(amount) FROM orders GROUP BY status", ALLOWED)


def test_reject_insert():
    with pytest.raises(SQLSecurityError):
        validate_sql("INSERT INTO users (name) VALUES ('test')", ALLOWED)


def test_reject_update():
    with pytest.raises(SQLSecurityError):
        validate_sql("UPDATE users SET name = 'x' WHERE id = 1", ALLOWED)


def test_reject_delete():
    with pytest.raises(SQLSecurityError):
        validate_sql("DELETE FROM users WHERE id = 1", ALLOWED)


def test_reject_drop():
    with pytest.raises(SQLSecurityError):
        validate_sql("DROP TABLE users", ALLOWED)


def test_reject_truncate():
    with pytest.raises(SQLSecurityError):
        validate_sql("TRUNCATE TABLE users", ALLOWED)


def test_reject_alter():
    with pytest.raises(SQLSecurityError):
        validate_sql("ALTER TABLE users ADD COLUMN foo INT", ALLOWED)


def test_reject_non_whitelisted_table():
    with pytest.raises(SQLSecurityError, match="secret_data"):
        validate_sql("SELECT * FROM secret_data", ALLOWED)


def test_reject_no_tables():
    with pytest.raises(SQLSecurityError, match="未能识别"):
        validate_sql("SELECT 1 + 1", ALLOWED)


def test_reject_exec():
    with pytest.raises(SQLSecurityError):
        validate_sql("EXEC sp_dangerous", ALLOWED)
