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

# Records created by tests inside the two demo schools (seed admission nos are SV/GP + 4 digits, seed teachers EMP1xx)
import re  # noqa: E402
demo = [str(s["_id"]) for s in db.schools.find({"slug": {"$in": ["sunrise-valley", "greenfield-public"]}})]
junk = [s for s in db.students.find({"school_id": {"$in": demo}}) if not re.match(r"^(SV|GP)\d{4}$", s["admission_no"])]
sids = [str(s["_id"]) for s in junk]
gids = db.guardian_links.distinct("guardian_id", {"student_id": {"$in": sids}})
db.guardian_links.delete_many({"student_id": {"$in": sids}})
db.students.delete_many({"_id": {"$in": [s["_id"] for s in junk]}})
orph_g = [ObjectId(g) for g in gids if not db.guardian_links.find_one({"guardian_id": g})]
db.guardians.delete_many({"_id": {"$in": orph_g}, "user_id": None})
tj = [t for t in db.teachers.find({"school_id": {"$in": demo}}) if not re.match(r"^EMP1\d\d$", t.get("employee_code") or "")]
db.teacher_assignments.delete_many({"teacher_id": {"$in": [str(t["_id"]) for t in tj]}})
db.teachers.delete_many({"_id": {"$in": [t["_id"] for t in tj]}})
db.invitations.delete_many({"school_id": {"$in": demo}})
db.users.delete_many({"email": {"$regex": "^(rl-|ghost-|shared-|restart-)"}})
db.login_limits.delete_many({})
print(f"removed {len(junk)} test students, {len(tj)} test teachers from demo schools")
