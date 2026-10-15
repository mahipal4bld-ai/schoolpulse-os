"""Idempotent fictional demo seed. All names are fictional. Runs only when DEMO_MODE=true."""
import random

from bson import ObjectId

from core import db, hash_password, now_utc
from routes_school import default_school

PASSWORD = "Demo@1234"

FIRST_M = ["Aarav", "Vihaan", "Arjun", "Reyansh", "Kabir", "Ishaan", "Advait", "Dhruv", "Krish", "Ayaan",
           "Rudra", "Atharv", "Shaurya", "Vivaan", "Aditya", "Pranav"]
FIRST_F = ["Ananya", "Diya", "Saanvi", "Myra", "Aadhya", "Kiara", "Ira", "Navya", "Riya", "Tara",
           "Meera", "Anika", "Prisha", "Avni", "Siya", "Zara"]
LAST = ["Sharma", "Verma", "Iyer", "Nair", "Reddy", "Gupta", "Mehta", "Kapoor", "Joshi", "Rao", "Das",
        "Bose", "Malhotra", "Chauhan", "Pillai", "Saxena"]
PARENT_M = ["Rakesh", "Sanjay", "Vikram", "Amit", "Rajiv", "Manoj", "Deepak", "Suresh"]

SCHOOLS = [
    {
        "slug": "sunrise-valley", "name": "Sunrise Valley Academy", "city": "Pune", "state": "Maharashtra",
        "tagline": "Rise. Learn. Lead.", "board": "CBSE",
        "description": "A co-educational CBSE school nurturing curious, confident learners since 2004.",
        "brand": {"primary": "#9A3412", "secondary": "#D97706", "monogram": "SV", "logo_style": "shield",
                  "welcome_message": "Good to see you at Sunrise Valley"},
        "classes": ["Class 1", "Class 2", "Class 3", "Class 4", "Class 5", "Class 6"], "per_section": 6,
        "subjects": [("English", "ENG"), ("Mathematics", "MATH"), ("Science", "SCI"), ("Hindi", "HIN"),
                     ("Social Studies", "SST"), ("Computer Science", "CS")],
        "domain": "sunrise.demo", "phone": "9820000001", "accent": "Sunrise",
        "teachers": ["Neha Kulkarni", "Rohit Deshpande", "Farah Sheikh", "Anil Patwardhan", "Kavita Menon",
                     "Sameer Joshi", "Pooja Bhatt", "Imran Qureshi"],
    },
    {
        "slug": "greenfield-public", "name": "Greenfield Public School", "city": "Jaipur", "state": "Rajasthan",
        "tagline": "Growing minds, rooted in values", "board": "ICSE",
        "description": "An ICSE day school with green campus learning and strong community values.",
        "brand": {"primary": "#14532D", "secondary": "#65A30D", "monogram": "GP", "logo_style": "circle",
                  "welcome_message": "Welcome to Greenfield"},
        "classes": ["Class 6", "Class 7", "Class 8", "Class 9", "Class 10"], "per_section": 5,
        "subjects": [("English", "ENG"), ("Mathematics", "MATH"), ("Physics", "PHY"), ("Chemistry", "CHEM"),
                     ("Biology", "BIO"), ("History & Civics", "HIST")],
        "domain": "greenfield.demo", "phone": "9414000001", "accent": "Greenfield",
        "teachers": ["Sunita Rathore", "Harish Agarwal", "Megha Shekhawat", "Vinod Choudhary", "Ritu Bansal",
                     "Karan Singhvi"],
    },
]


async def _user(email, name, order, label, platform_role=None):
    await db.users.update_one({"email": email}, {"$setOnInsert": {
        "email": email, "name": name, "password_hash": hash_password(PASSWORD), "status": "active",
        "platform_role": platform_role, "preferred_language": "en", "is_demo": True, "demo_order": order,
        "demo_label": label, "created_at": now_utc()}}, upsert=True)
    return str((await db.users.find_one({"email": email}))["_id"])


async def _member(uid, sid, role):
    await db.memberships.update_one({"user_id": uid, "school_id": sid},
                                    {"$setOnInsert": {"role": role, "status": "active", "created_at": now_utc()}},
                                    upsert=True)


async def seed():
    await _user("superadmin@schoolpulse.demo", "Platform Admin", 0, "SchoolPulse Super Admin", "super_admin")
    multi_uid = await _user("multi.parent@schoolpulse.demo", "Rakesh Malhotra", 99, "Parent (both schools)")
    order = 1
    for cfg in SCHOOLS:
        rnd = random.Random(cfg["slug"])
        if await db.schools.find_one({"slug": cfg["slug"]}):
            order += 10
            continue
        doc = default_school(cfg["name"], cfg["slug"], cfg["city"], "growth", 1500)
        doc.update({"tagline": cfg["tagline"], "description": cfg["description"], "board": cfg["board"],
                    "academic_session_label": "2025-26"})
        doc["brand"].update(cfg["brand"])
        doc["contact"].update({"phone": cfg["phone"], "email": f"office@{cfg['domain']}", "state": cfg["state"],
                               "address": f"Plot 12, Knowledge Park, {cfg['city']}",
                               "website": f"https://{cfg['domain']}", "pincode": "411001" if cfg["city"] == "Pune" else "302001"})
        sid = str((await db.schools.insert_one(doc)).inserted_id)
        d = cfg["domain"]
        roles = [("owner", f"owner@{d}", f"{cfg['accent']} Owner", "School Owner"),
                 ("principal", f"principal@{d}", f"{cfg['accent']} Principal", "Principal"),
                 ("school_admin", f"admin@{d}", f"{cfg['accent']} Admin", "School Administrator"),
                 ("accountant", f"accountant@{d}", f"{cfg['accent']} Accounts", "Accountant")]
        for role, email, name, label in roles:
            await _member(await _user(email, name, order, f"{label} · {cfg['name']}"), sid, role)
            order += 1
        year = await db.academic_years.insert_one({"school_id": sid, "name": "2025-26", "start_date": "2025-04-01",
                                                   "end_date": "2026-03-31", "is_current": True, "created_at": now_utc()})
        year_id = str(year.inserted_id)
        subj_ids = []
        for n, c in cfg["subjects"]:
            subj_ids.append(str((await db.subjects.insert_one({"school_id": sid, "name": n, "code": c,
                                                               "created_at": now_utc()})).inserted_id))
        teacher_ids = []
        for i, tname in enumerate(cfg["teachers"]):
            email = f"{tname.split()[0].lower()}.{tname.split()[1].lower()}@{d}"
            uid = None
            if i == 0:
                uid = await _user(f"teacher@{d}", tname, order, f"Teacher · {cfg['name']}")
                order += 1
                await _member(uid, sid, "teacher")
                email = f"teacher@{d}"
            teacher_ids.append(str((await db.teachers.insert_one({
                "school_id": sid, "name": tname, "email": email, "phone": f"98{rnd.randint(10000000, 99999999)}",
                "designation": "Senior Teacher" if i < 2 else "Teacher", "employee_code": f"EMP{100 + i}",
                "status": "active", "user_id": uid, "created_at": now_utc()})).inserted_id))
        parent_uid = await _user(f"parent@{d}", f"{rnd.choice(PARENT_M)} {rnd.choice(LAST)}", order,
                                 f"Parent · {cfg['name']}")
        order += 1
        await _member(parent_uid, sid, "parent")
        await _member(multi_uid, sid, "parent")
        adm = 1000
        first_sections = []
        for ci, cname in enumerate(cfg["classes"]):
            cid = str((await db.classes.insert_one({"school_id": sid, "academic_year_id": year_id, "name": cname,
                                                    "order": ci + 1, "created_at": now_utc()})).inserted_id)
            for sname in ["A", "B"]:
                ct = teacher_ids[(ci * 2 + (sname == "B")) % len(teacher_ids)]
                sec_id = str((await db.sections.insert_one({"school_id": sid, "class_id": cid, "name": sname,
                                                            "class_name": cname, "capacity": 40, "class_teacher_id": ct,
                                                            "created_at": now_utc()})).inserted_id)
                first_sections.append(sec_id)
                await db.teacher_assignments.insert_one({"school_id": sid, "teacher_id": ct, "section_id": sec_id,
                                                         "class_id": cid, "subject_id": subj_ids[0],
                                                         "is_class_teacher": True, "created_at": now_utc()})
                for k in range(cfg["per_section"]):
                    adm += 1
                    gender = "female" if rnd.random() < 0.5 else "male"
                    fn = rnd.choice(FIRST_F if gender == "female" else FIRST_M)
                    ln = rnd.choice(LAST)
                    base_year = 2019 - ci - (5 if cfg["slug"] == "greenfield-public" else 0)
                    st = await db.students.insert_one({
                        "school_id": sid, "admission_no": f"{cfg['brand']['monogram']}{adm}",
                        "first_name": fn, "last_name": ln, "gender": gender,
                        "dob": f"{base_year}-{rnd.randint(1, 12):02d}-{rnd.randint(1, 28):02d}",
                        "section_id": sec_id, "class_id": cid, "academic_year_id": year_id, "class_name": cname,
                        "section_name": sname, "roll_no": k + 1, "status": "active", "created_at": now_utc()})
                    gname = f"{rnd.choice(PARENT_M)} {ln}"
                    g = await db.guardians.insert_one({"school_id": sid, "name": gname,
                                                       "phone": f"9{rnd.randint(100000000, 999999999)}",
                                                       "email": None, "user_id": None, "occupation": "",
                                                       "created_at": now_utc()})
                    await db.guardian_links.insert_one({
                        "school_id": sid, "student_id": str(st.inserted_id), "guardian_id": str(g.inserted_id),
                        "relation": "father", "verified": rnd.random() < 0.8, "consents": {"photo": False},
                        "created_at": now_utc()})
        # demo teacher teaches additional subjects
        t0 = teacher_ids[0]
        for j, sec_id in enumerate(first_sections[2:5]):
            sec = await db.sections.find_one({"_id": ObjectId(sec_id)})
            await db.teacher_assignments.update_one(
                {"school_id": sid, "teacher_id": t0, "section_id": sec_id, "subject_id": subj_ids[1 + j % 3]},
                {"$setOnInsert": {"class_id": sec["class_id"], "is_class_teacher": False, "created_at": now_utc()}},
                upsert=True)
        # link demo parents to verified children
        kids = await db.students.find({"school_id": sid}).sort("admission_no", 1).limit(3).to_list(3)
        for idx, (uid, email, kid_list) in enumerate([(parent_uid, f"parent@{d}", kids[:2]),
                                                      (multi_uid, "multi.parent@schoolpulse.demo", kids[2:3])]):
            u = await db.users.find_one({"email": email})
            g = await db.guardians.insert_one({"school_id": sid, "name": u["name"], "phone": f"99{rnd.randint(10000000, 99999999)}",
                                               "email": email, "user_id": uid, "occupation": "Business",
                                               "created_at": now_utc()})
            for kid in kid_list:
                await db.guardian_links.insert_one({
                    "school_id": sid, "student_id": str(kid["_id"]), "guardian_id": str(g.inserted_id),
                    "relation": "father", "verified": True, "verified_at": now_utc(),
                    "consents": {"photo": True, "recorded_at": now_utc()}, "created_at": now_utc()})
        order += 10
