"""Backup & restore proof for SchoolPulse OS (MongoDB).

  python scripts/backup_restore.py backup                 -> /app/backups/<ts>/ (mongodump --gzip + manifest.json)
  python scripts/backup_restore.py verify <backup_dir>    -> restores into a CLEAN db `<DB>_restore_verify`,
                                                             compares manifest vs restored data, writes report
Never point this at customer production data for drills.
"""
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
URL, DB = os.environ["MONGO_URL"], os.environ["DB_NAME"]
COLLS = ["schools", "users", "memberships", "academic_years", "classes", "sections", "subjects", "teachers",
         "teacher_assignments", "students", "guardians", "guardian_links", "files", "invitations", "audit_logs"]


def fingerprint(db) -> dict:
    """Counts + content hashes of the data that must survive a restore."""
    fp = {"counts": {c: db[c].count_documents({}) for c in COLLS}, "schools": {}}
    for s in db.schools.find().sort("slug", 1):
        sid = str(s["_id"])
        fp["schools"][s["slug"]] = {
            "brand": s.get("brand"), "name": s["name"], "status": s.get("status"),
            "students": db.students.count_documents({"school_id": sid}),
            "teachers": db.teachers.count_documents({"school_id": sid}),
            "guardian_links_verified": db.guardian_links.count_documents({"school_id": sid, "verified": True}),
            "assignments": db.teacher_assignments.count_documents({"school_id": sid}),
            "files": sorted(f["storage_path"] for f in db.files.find({"school_id": sid})),
            "roles": sorted(f"{m['user_id']}:{m['role']}" for m in db.memberships.find({"school_id": sid})),
        }
    h = hashlib.sha256()
    for c in ["students", "guardian_links", "teacher_assignments", "users"]:
        for d in db[c].find({}, {"_id": 1, "password_hash": 1, "section_id": 1, "student_id": 1, "guardian_id": 1,
                                 "teacher_id": 1, "admission_no": 1}).sort("_id", 1):
            h.update(json.dumps(d, default=str, sort_keys=True).encode())
    fp["relationship_hash"] = h.hexdigest()
    return fp


def backup():
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path("/app/backups") / ts
    out.mkdir(parents=True)
    subprocess.run(["mongodump", f"--uri={URL}", f"--db={DB}", "--gzip", f"--out={out}"], check=True, capture_output=True)
    manifest = {"created_at": ts, "source_db": DB, "fingerprint": fingerprint(MongoClient(URL)[DB])}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    print(out)
    return out


def verify(path: str):
    out = Path(path)
    manifest = json.loads((out / "manifest.json").read_text())
    target = f"{DB}_restore_verify"
    cli = MongoClient(URL)
    cli.drop_database(target)  # clean environment
    assert target not in cli.list_database_names()
    subprocess.run(["mongorestore", f"--uri={URL}", "--gzip", f"--nsFrom={DB}.*", f"--nsTo={target}.*",
                    "--drop", str(out)], check=True, capture_output=True)
    restored = json.loads(json.dumps(fingerprint(cli[target]), default=str))
    expected = manifest["fingerprint"]
    diffs = [k for k in expected if expected[k] != restored.get(k)]
    report = {"verified_at": datetime.now(timezone.utc).isoformat(), "backup": str(out), "restored_db": target,
              "result": "PASS" if not diffs else "FAIL", "mismatched_sections": diffs,
              "counts": restored["counts"],
              "schools": {k: {x: v[x] for x in ("students", "teachers", "assignments", "guardian_links_verified")}
                          | {"brand_primary": v["brand"]["primary"], "files": len(v["files"]), "roles": len(v["roles"])}
                          for k, v in restored["schools"].items()}}
    (out / "restore_report.json").write_text(json.dumps(report, indent=2))
    cli.drop_database(target)
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    if sys.argv[1] == "backup":
        backup()
    else:
        sys.exit(0 if verify(sys.argv[2])["result"] == "PASS" else 1)
