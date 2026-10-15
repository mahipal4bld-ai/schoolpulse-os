"""Remove tenants created by automated tests (slugs starting with test-/edge-/audit-) and their records.
Usage: cd /app/backend && python scripts/cleanup_test_data.py"""
import os

from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
rx = {"$regex": "^(test-|edge-|audit-)"}
ids = [str(s["_id"]) for s in db.schools.find({"slug": rx})]
owner_ids = db.memberships.distinct("user_id", {"school_id": {"$in": ids}})
for c in db.list_collection_names():
    if c != "schools":
        db[c].delete_many({"school_id": {"$in": ids}})
db.schools.delete_many({"slug": rx})
orphans = [u for u in owner_ids if not db.memberships.find_one({"user_id": u})]
db.users.delete_many({"_id": {"$in": [ObjectId(u) for u in orphans]}, "is_demo": {"$ne": True}, "platform_role": None})
print(f"removed {len(ids)} test schools, {len(orphans)} orphan users; schools now {db.schools.count_documents({})}")
