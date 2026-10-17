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


@pytest.fixture(autouse=True)
def _serialize_shared_academic_state(request):
    """M2/audit suites mutate the same demo section (attendance, homework, exams, timetable). Under xdist they would
    race across workers, so they take a cross-process lock; other suites keep running in parallel."""
    name = request.module.__name__.rsplit(".", 1)[-1]
    if not name.startswith(("test_m2_", "test_audit_")):
        yield
        return
    import fcntl
    with open("/tmp/schoolpulse-academic-tests.lock", "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
