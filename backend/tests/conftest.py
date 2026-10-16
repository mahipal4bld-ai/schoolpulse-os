"""Session-wide test hygiene: clear login rate-limit buckets so earlier lock-outs don't cascade across suites."""
import os

import pytest
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))


@pytest.fixture(scope="session", autouse=True)
def _reset_login_limits():
    MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]].login_limits.delete_many({})
    yield
