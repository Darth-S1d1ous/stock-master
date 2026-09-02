import os

# Unit and API tests import the application database module during collection.
# Supply inert test-only defaults so they do not depend on a developer's .env.
os.environ.setdefault("POSTGRES_USER", "stock_master_test")
os.environ.setdefault("POSTGRES_PASSWORD", "stock_master_test_password")
os.environ.setdefault("POSTGRES_DB", "stock_master_test")
os.environ.setdefault("POSTGRES_HOST", "127.0.0.1")
os.environ.setdefault("POSTGRES_PORT", "5432")
