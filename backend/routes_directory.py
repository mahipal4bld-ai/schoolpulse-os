"""Academic directory: years, classes, sections, subjects, teachers, students, guardians,
guardian links, teacher assignments, CSV import, teacher workspace and parent portal."""
import csv
import io
import re
from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field, field_validator

from core import Ctx, audit, db, need, now_utc, oid, out, school_ctx

router = APIRouter()


def page_params(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), q: str = Query("", max_length=80)):
    return {"page": page, "page_size": page_size, "q": q.strip()}


async def paginate(coll, filt: dict, p: dict, sort: list, search_fields: list[str]):
    if p["q"] and search_fields:
        rx = {"$regex": re.escape(p["q"]), "$options": "i"}
        filt = {**filt, "$or": [{f: rx} for f in search_fields]}
    total = await coll.count_documents(filt)
    docs = await coll.find(filt).sort(sort).skip((p["page"] - 1) * p["page_size"]).limit(p["page_size"]).to_list(p["page_size"])
    return {"items": [out(d) for d in docs], "total": total, "page": p["page"], "page_size": p["page_size"],
            "has_more": p["page"] * p["page_size"] < total}


async def ref(coll_name: str, rid: Optional[str], school_id: str, label: str) -> Optional[dict]:
    if not rid:
        return None
    from bson import ObjectId
    if not ObjectId.is_valid(rid):
        raise HTTPException(400, f"Invalid {label}")
    d = await db[coll_name].find_one({"_id": ObjectId(rid), "school_id": school_id})
    if not d:
        raise HTTPException(400, f"{label} not found in this school")
    return d


async def get_owned(coll_name: str, rid: str, school_id: str) -> dict:
    d = await db[coll_name].find_one({"_id": oid(rid), "school_id": school_id})
    if not d:
        raise HTTPException(404, "Record not found")
    return d


async def insert(ctx: Ctx, coll_name: str, data: dict, entity: str) -> dict:
    doc = {**data, "school_id": ctx.school_id, "created_at": now_utc(), "created_by": ctx.user_id}
    r = await db[coll_name].insert_one(doc)
    doc["_id"] = r.inserted_id
    await audit(ctx.user_id, f"{entity}.create", entity, str(r.inserted_id), ctx.school_id)
    return out(doc)


async def update(ctx: Ctx, coll_name: str, rid: str, data: dict, entity: str) -> dict:
    if not data:
        raise HTTPException(400, "No changes supplied")
    await get_owned(coll_name, rid, ctx.school_id)
    await db[coll_name].update_one({"_id": oid(rid), "school_id": ctx.school_id},
                                   {"$set": {**data, "updated_at": now_utc()}})
    await audit(ctx.user_id, f"{entity}.update", entity, rid, ctx.school_id, {"fields": list(data)})
    return out(await db[coll_name].find_one({"_id": oid(rid)}))


async def delete(ctx: Ctx, coll_name: str, rid: str, entity: str, blockers: list[tuple[str, str, str]]):
    await get_owned(coll_name, rid, ctx.school_id)
    for coll, field, label in blockers:
        if await db[coll].count_documents({"school_id": ctx.school_id, field: rid}):
            raise HTTPException(409, f"Cannot delete: {label} still linked to this record")
    await db[coll_name].delete_one({"_id": oid(rid), "school_id": ctx.school_id})
    await audit(ctx.user_id, f"{entity}.delete", entity, rid, ctx.school_id)
    return {"ok": True}


# ---------------------------------------------------------------- academic years
class YearIn(BaseModel):
    name: str = Field(min_length=4, max_length=20, pattern=r"^\d{4}-\d{2}$")
    start_date: date
    end_date: date
    is_current: bool = False

    @field_validator("end_date")
    @classmethod
    def _order(cls, v, info):
        s = info.data.get("start_date")
        if s and v <= s:
            raise ValueError("End date must be after start date")
        return v


class YearPatch(BaseModel):
    is_current: Optional[bool] = None


@router.get("/academic-years")
async def list_years(p=Depends(page_params), ctx: Ctx = Depends(need("academic.view"))):
    return await paginate(db.academic_years, {"school_id": ctx.school_id}, p, [("start_date", -1)], ["name"])


@router.post("/academic-years", status_code=201)
async def create_year(body: YearIn, ctx: Ctx = Depends(need("academic.manage"))):
    data = body.model_dump()
    data["start_date"], data["end_date"] = str(body.start_date), str(body.end_date)
    if body.is_current:
        await db.academic_years.update_many({"school_id": ctx.school_id}, {"$set": {"is_current": False}})
    res = await insert(ctx, "academic_years", data, "academic_year")
    if body.is_current:
        await db.schools.update_one({"_id": oid(ctx.school_id)}, {"$set": {"academic_session_label": body.name}})
    return res


@router.patch("/academic-years/{rid}")
async def patch_year(rid: str, body: YearPatch, ctx: Ctx = Depends(need("academic.manage"))):
    if body.is_current:
        y = await get_owned("academic_years", rid, ctx.school_id)
        await db.academic_years.update_many({"school_id": ctx.school_id}, {"$set": {"is_current": False}})
        await db.schools.update_one({"_id": oid(ctx.school_id)}, {"$set": {"academic_session_label": y["name"]}})
    return await update(ctx, "academic_years", rid, body.model_dump(exclude_none=True), "academic_year")


@router.delete("/academic-years/{rid}")
async def delete_year(rid: str, ctx: Ctx = Depends(need("academic.manage"))):
    return await delete(ctx, "academic_years", rid, "academic_year", [("classes", "academic_year_id", "classes")])


# ---------------------------------------------------------------- classes
class ClassIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    academic_year_id: str
    order: int = Field(default=0, ge=0, le=100)


class ClassPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=40)
    order: Optional[int] = Field(default=None, ge=0, le=100)


async def _class_out(c: dict, school_id: str) -> dict:
    sections = await db.sections.find({"school_id": school_id, "class_id": c["id"]}).sort("name", 1).to_list(50)
    c["sections"] = [out(s) for s in sections]
    c["student_count"] = await db.students.count_documents({"school_id": school_id, "class_id": c["id"], "status": "active"})
    return c


@router.get("/classes")
async def list_classes(academic_year_id: Optional[str] = None, p=Depends(page_params),
                       ctx: Ctx = Depends(need("academic.view"))):
    filt = {"school_id": ctx.school_id}
    if academic_year_id:
        filt["academic_year_id"] = academic_year_id
    res = await paginate(db.classes, filt, p, [("order", 1), ("name", 1)], ["name"])
    res["items"] = [await _class_out(c, ctx.school_id) for c in res["items"]]
    return res


@router.post("/classes", status_code=201)
async def create_class(body: ClassIn, ctx: Ctx = Depends(need("academic.manage"))):
    await ref("academic_years", body.academic_year_id, ctx.school_id, "Academic year")
    return await _class_out(await insert(ctx, "classes", body.model_dump(), "class"), ctx.school_id)


@router.patch("/classes/{rid}")
async def patch_class(rid: str, body: ClassPatch, ctx: Ctx = Depends(need("academic.manage"))):
    return await update(ctx, "classes", rid, body.model_dump(exclude_none=True), "class")


@router.delete("/classes/{rid}")
async def delete_class(rid: str, ctx: Ctx = Depends(need("academic.manage"))):
    return await delete(ctx, "classes", rid, "class", [("sections", "class_id", "sections")])


# ---------------------------------------------------------------- sections
class SectionIn(BaseModel):
    class_id: str
    name: str = Field(min_length=1, max_length=10)
    capacity: int = Field(default=40, ge=1, le=120)


class SectionPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=10)
    capacity: Optional[int] = Field(default=None, ge=1, le=120)


@router.get("/sections")
async def list_sections(class_id: Optional[str] = None, p=Depends(page_params), ctx: Ctx = Depends(need("academic.view"))):
    filt = {"school_id": ctx.school_id}
    if class_id:
        filt["class_id"] = class_id
    return await paginate(db.sections, filt, p, [("name", 1)], ["name"])


@router.post("/sections", status_code=201)
async def create_section(body: SectionIn, ctx: Ctx = Depends(need("academic.manage"))):
    c = await ref("classes", body.class_id, ctx.school_id, "Class")
    data = body.model_dump()
    data["name"] = data["name"].upper()
    data["class_name"] = c["name"]
    return await insert(ctx, "sections", data, "section")


@router.patch("/sections/{rid}")
async def patch_section(rid: str, body: SectionPatch, ctx: Ctx = Depends(need("academic.manage"))):
    data = body.model_dump(exclude_none=True)
    if "name" in data:
        data["name"] = data["name"].upper()
    return await update(ctx, "sections", rid, data, "section")


@router.delete("/sections/{rid}")
async def delete_section(rid: str, ctx: Ctx = Depends(need("academic.manage"))):
    return await delete(ctx, "sections", rid, "section", [("students", "section_id", "students"),
                                                          ("teacher_assignments", "section_id", "teacher assignments")])


# ---------------------------------------------------------------- subjects
class SubjectIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    code: str = Field(min_length=2, max_length=12, pattern=r"^[A-Za-z0-9-]+$")


class SubjectPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=60)


@router.get("/subjects")
async def list_subjects(p=Depends(page_params), ctx: Ctx = Depends(need("academic.view"))):
    return await paginate(db.subjects, {"school_id": ctx.school_id}, p, [("name", 1)], ["name", "code"])


@router.post("/subjects", status_code=201)
async def create_subject(body: SubjectIn, ctx: Ctx = Depends(need("academic.manage"))):
    data = body.model_dump()
    data["code"] = data["code"].upper()
    return await insert(ctx, "subjects", data, "subject")


@router.patch("/subjects/{rid}")
async def patch_subject(rid: str, body: SubjectPatch, ctx: Ctx = Depends(need("academic.manage"))):
    return await update(ctx, "subjects", rid, body.model_dump(exclude_none=True), "subject")


@router.delete("/subjects/{rid}")
async def delete_subject(rid: str, ctx: Ctx = Depends(need("academic.manage"))):
    return await delete(ctx, "subjects", rid, "subject", [("teacher_assignments", "subject_id", "teacher assignments")])


# ---------------------------------------------------------------- teachers
PHONE = r"^[6-9]\d{9}$"


class TeacherIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    phone: str = Field(pattern=PHONE)
    designation: str = Field(default="Teacher", max_length=60)
    employee_code: str = Field(default="", max_length=20)


class TeacherPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    phone: Optional[str] = Field(default=None, pattern=PHONE)
    designation: Optional[str] = Field(default=None, max_length=60)
    status: Optional[Literal["active", "inactive"]] = None


async def _teacher_out(t: dict, school_id: str) -> dict:
    asg = await db.teacher_assignments.find({"school_id": school_id, "teacher_id": t["id"]}).to_list(100)
    t["assignments"] = [await _assignment_out(out(a)) for a in asg]
    return t


@router.get("/teachers")
async def list_teachers(p=Depends(page_params), ctx: Ctx = Depends(need("people.view"))):
    res = await paginate(db.teachers, {"school_id": ctx.school_id}, p, [("name", 1)], ["name", "email", "employee_code"])
    res["items"] = [await _teacher_out(t, ctx.school_id) for t in res["items"]]
    return res


@router.get("/teachers/{rid}")
async def get_teacher(rid: str, ctx: Ctx = Depends(need("people.view"))):
    return await _teacher_out(out(await get_owned("teachers", rid, ctx.school_id)), ctx.school_id)


@router.post("/teachers", status_code=201)
async def create_teacher(body: TeacherIn, ctx: Ctx = Depends(need("staff.manage"))):
    data = body.model_dump()
    data["email"] = data["email"].lower()
    data["status"] = "active"
    data["user_id"] = None
    return await _teacher_out(await insert(ctx, "teachers", data, "teacher"), ctx.school_id)


@router.patch("/teachers/{rid}")
async def patch_teacher(rid: str, body: TeacherPatch, ctx: Ctx = Depends(need("staff.manage"))):
    return await update(ctx, "teachers", rid, body.model_dump(exclude_none=True), "teacher")


@router.delete("/teachers/{rid}")
async def delete_teacher(rid: str, ctx: Ctx = Depends(need("staff.manage"))):
    return await delete(ctx, "teachers", rid, "teacher", [("teacher_assignments", "teacher_id", "class assignments")])


# ---------------------------------------------------------------- teacher assignments
class AssignmentIn(BaseModel):
    teacher_id: str
    section_id: str
    subject_id: Optional[str] = None
    is_class_teacher: bool = False


async def _assignment_out(a: dict) -> dict:
    s = await db.sections.find_one({"_id": oid(a["section_id"])}) if a.get("section_id") else None
    sub = await db.subjects.find_one({"_id": oid(a["subject_id"])}) if a.get("subject_id") else None
    a["section_label"] = f"{s.get('class_name')} - {s.get('name')}" if s else None
    a["subject_name"] = sub["name"] if sub else None
    return a


@router.post("/teacher-assignments", status_code=201)
async def create_assignment(body: AssignmentIn, ctx: Ctx = Depends(need("academic.manage"))):
    await ref("teachers", body.teacher_id, ctx.school_id, "Teacher")
    sec = await ref("sections", body.section_id, ctx.school_id, "Section")
    await ref("subjects", body.subject_id, ctx.school_id, "Subject")
    if body.is_class_teacher:
        await db.teacher_assignments.update_many({"school_id": ctx.school_id, "section_id": body.section_id},
                                                 {"$set": {"is_class_teacher": False}})
        await db.sections.update_one({"_id": sec["_id"]}, {"$set": {"class_teacher_id": body.teacher_id}})
    data = body.model_dump()
    data["class_id"] = sec["class_id"]
    return await _assignment_out(await insert(ctx, "teacher_assignments", data, "teacher_assignment"))


@router.get("/teacher-assignments")
async def list_assignments(teacher_id: Optional[str] = None, section_id: Optional[str] = None,
                           ctx: Ctx = Depends(need("academic.view"))):
    filt = {"school_id": ctx.school_id}
    if teacher_id:
        filt["teacher_id"] = teacher_id
    if section_id:
        filt["section_id"] = section_id
    docs = await db.teacher_assignments.find(filt).to_list(500)
    return {"items": [await _assignment_out(out(d)) for d in docs]}


@router.delete("/teacher-assignments/{rid}")
async def delete_assignment(rid: str, ctx: Ctx = Depends(need("academic.manage"))):
    return await delete(ctx, "teacher_assignments", rid, "teacher_assignment", [])


# ---------------------------------------------------------------- students
class StudentIn(BaseModel):
    admission_no: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9/-]+$")
    first_name: str = Field(min_length=1, max_length=60)
    last_name: str = Field(default="", max_length=60)
    gender: Literal["male", "female", "other"]
    dob: date
    section_id: str
    roll_no: Optional[int] = Field(default=None, ge=1, le=200)

    @field_validator("dob")
    @classmethod
    def _dob(cls, v):
        if v >= date.today() or v.year < 1995:
            raise ValueError("Enter a valid date of birth")
        return v


class StudentPatch(BaseModel):
    first_name: Optional[str] = Field(default=None, min_length=1, max_length=60)
    last_name: Optional[str] = Field(default=None, max_length=60)
    gender: Optional[Literal["male", "female", "other"]] = None
    section_id: Optional[str] = None
    roll_no: Optional[int] = Field(default=None, ge=1, le=200)
    status: Optional[Literal["active", "archived"]] = None


async def teacher_section_ids(ctx: Ctx) -> list[str]:
    t = await db.teachers.find_one({"school_id": ctx.school_id, "user_id": ctx.user_id})
    if not t:
        return []
    return await db.teacher_assignments.distinct("section_id", {"school_id": ctx.school_id, "teacher_id": str(t["_id"])})


async def _student_placement(section_id: str, school_id: str) -> dict:
    sec = await ref("sections", section_id, school_id, "Section")
    cls = await db.classes.find_one({"_id": oid(sec["class_id"])})
    return {"section_id": section_id, "class_id": sec["class_id"], "academic_year_id": cls["academic_year_id"],
            "class_name": cls["name"], "section_name": sec["name"]}


@router.get("/students")
async def list_students(section_id: Optional[str] = None, class_id: Optional[str] = None,
                        status: Literal["active", "archived"] = "active",
                        p=Depends(page_params), ctx: Ctx = Depends(school_ctx)):
    filt = {"school_id": ctx.school_id, "status": status}
    if "people.view" not in ctx.perms:
        if "teacher.workspace" not in ctx.perms:
            raise HTTPException(403, "Not permitted to view the student directory")
        allowed = await teacher_section_ids(ctx)
        if section_id and section_id not in allowed:
            raise HTTPException(403, "You are not assigned to this section")
        filt["section_id"] = {"$in": allowed}
    if section_id:
        filt["section_id"] = section_id
    if class_id:
        filt["class_id"] = class_id
    return await paginate(db.students, filt, p, [("class_name", 1), ("section_name", 1), ("roll_no", 1), ("first_name", 1)],
                          ["first_name", "last_name", "admission_no"])


@router.get("/students/{rid}")
async def get_student(rid: str, ctx: Ctx = Depends(school_ctx)):
    s = await get_owned("students", rid, ctx.school_id)
    if "people.view" not in ctx.perms:
        if "teacher.workspace" not in ctx.perms or s["section_id"] not in await teacher_section_ids(ctx):
            raise HTTPException(403, "Not permitted to view this student")
    d = out(s)
    links = await db.guardian_links.find({"school_id": ctx.school_id, "student_id": rid}).to_list(20)
    d["guardians"] = []
    for link in links:
        g = await db.guardians.find_one({"_id": oid(link["guardian_id"])})
        d["guardians"].append({**out(link), "guardian": out(g)})
    return d


@router.post("/students", status_code=201)
async def create_student(body: StudentIn, ctx: Ctx = Depends(need("people.manage"))):
    school = await db.schools.find_one({"_id": oid(ctx.school_id)})
    if await db.students.count_documents({"school_id": ctx.school_id, "status": "active"}) >= school.get("student_quota", 1500):
        raise HTTPException(402, "Student quota for your plan has been reached")
    data = body.model_dump()
    data["dob"] = str(body.dob)
    data["admission_no"] = data["admission_no"].upper()
    data.update(await _student_placement(body.section_id, ctx.school_id))
    data["status"] = "active"
    return await insert(ctx, "students", data, "student")


@router.patch("/students/{rid}")
async def patch_student(rid: str, body: StudentPatch, ctx: Ctx = Depends(need("people.manage"))):
    data = body.model_dump(exclude_none=True)
    if "section_id" in data:
        data.update(await _student_placement(data["section_id"], ctx.school_id))
    return await update(ctx, "students", rid, data, "student")


@router.delete("/students/{rid}")
async def archive_student(rid: str, ctx: Ctx = Depends(need("people.manage"))):
    """Soft delete (archive) for data-retention compliance. Hard purge is a separate audited workflow."""
    return await update(ctx, "students", rid, {"status": "archived", "archived_at": now_utc()}, "student")


# ---------------------------------------------------------------- guardians & links
class GuardianIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    phone: str = Field(pattern=PHONE)
    email: Optional[EmailStr] = None
    occupation: str = Field(default="", max_length=60)


class LinkIn(BaseModel):
    student_id: str
    guardian_id: Optional[str] = None
    guardian: Optional[GuardianIn] = None
    relation: Literal["father", "mother", "guardian", "grandparent", "other"]
    verified: bool = False
    photo_consent: bool = False


class LinkPatch(BaseModel):
    verified: Optional[bool] = None
    photo_consent: Optional[bool] = None


@router.get("/guardians")
async def list_guardians(p=Depends(page_params), ctx: Ctx = Depends(need("people.view"))):
    return await paginate(db.guardians, {"school_id": ctx.school_id}, p, [("name", 1)], ["name", "phone", "email"])


@router.post("/guardians", status_code=201)
async def create_guardian(body: GuardianIn, ctx: Ctx = Depends(need("people.manage"))):
    data = body.model_dump()
    data["email"] = (data["email"] or "").lower() or None
    data["user_id"] = await _match_user(data["email"])
    return await insert(ctx, "guardians", data, "guardian")


async def _match_user(email: Optional[str]) -> Optional[str]:
    if not email:
        return None
    u = await db.users.find_one({"email": email})
    return str(u["_id"]) if u else None


@router.post("/guardian-links", status_code=201)
async def link_guardian(body: LinkIn, ctx: Ctx = Depends(need("people.manage"))):
    await ref("students", body.student_id, ctx.school_id, "Student")
    if body.guardian_id:
        g = await ref("guardians", body.guardian_id, ctx.school_id, "Guardian")
        gid = str(g["_id"])
    elif body.guardian:
        existing = await db.guardians.find_one({"school_id": ctx.school_id, "phone": body.guardian.phone})
        gid = str(existing["_id"]) if existing else (await create_guardian(body.guardian, ctx))["id"]
    else:
        raise HTTPException(400, "Provide guardian_id or guardian details")
    if await db.guardian_links.find_one({"student_id": body.student_id, "guardian_id": gid}):
        raise HTTPException(409, "This guardian is already linked to the student")
    data = {"student_id": body.student_id, "guardian_id": gid, "relation": body.relation, "verified": body.verified,
            "verified_by": ctx.user_id if body.verified else None, "verified_at": now_utc() if body.verified else None,
            "consents": {"photo": body.photo_consent, "recorded_at": now_utc(), "recorded_by": ctx.user_id}}
    return await insert(ctx, "guardian_links", data, "guardian_link")


@router.patch("/guardian-links/{rid}")
async def patch_link(rid: str, body: LinkPatch, ctx: Ctx = Depends(need("people.manage"))):
    data = {}
    if body.verified is not None:
        data.update({"verified": body.verified, "verified_by": ctx.user_id, "verified_at": now_utc()})
    if body.photo_consent is not None:
        data.update({"consents.photo": body.photo_consent, "consents.recorded_at": now_utc(),
                     "consents.recorded_by": ctx.user_id})
    return await update(ctx, "guardian_links", rid, data, "guardian_link")


@router.delete("/guardian-links/{rid}")
async def unlink(rid: str, ctx: Ctx = Depends(need("people.manage"))):
    return await delete(ctx, "guardian_links", rid, "guardian_link", [])


# ---------------------------------------------------------------- CSV import
class ImportIn(BaseModel):
    csv_text: str = Field(min_length=10, max_length=500_000)
    dry_run: bool = True


CSV_COLUMNS = ["admission_no", "first_name", "last_name", "gender", "dob", "class", "section",
               "guardian_name", "guardian_phone", "guardian_relation"]


@router.post("/students/import")
async def import_students(body: ImportIn, ctx: Ctx = Depends(need("people.manage"))):
    reader = csv.DictReader(io.StringIO(body.csv_text.strip()))
    missing = [c for c in CSV_COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        raise HTTPException(400, f"Missing columns: {', '.join(missing)}")
    year = await db.academic_years.find_one({"school_id": ctx.school_id, "is_current": True})
    if not year:
        raise HTTPException(400, "Set a current academic year before importing")
    rows, errors, created = list(reader), [], 0
    seen = set()
    for i, row in enumerate(rows, start=2):
        try:
            adm = (row["admission_no"] or "").strip().upper()
            if not adm or adm in seen:
                raise ValueError("Missing or duplicate admission_no in file")
            seen.add(adm)
            if await db.students.find_one({"school_id": ctx.school_id, "admission_no": adm}):
                raise ValueError("admission_no already exists")
            cls = await db.classes.find_one({"school_id": ctx.school_id, "academic_year_id": str(year["_id"]),
                                             "name": row["class"].strip()})
            if not cls:
                raise ValueError(f"Class '{row['class']}' not found")
            sec = await db.sections.find_one({"school_id": ctx.school_id, "class_id": str(cls["_id"]),
                                              "name": row["section"].strip().upper()})
            if not sec:
                raise ValueError(f"Section '{row['section']}' not found")
            student = StudentIn(admission_no=adm, first_name=row["first_name"].strip(),
                                last_name=(row["last_name"] or "").strip(), gender=row["gender"].strip().lower(),
                                dob=row["dob"].strip(), section_id=str(sec["_id"]))
            guardian = GuardianIn(name=row["guardian_name"].strip(), phone=row["guardian_phone"].strip())
            relation = (row["guardian_relation"] or "guardian").strip().lower()
            if relation not in ["father", "mother", "guardian", "grandparent", "other"]:
                raise ValueError("Invalid guardian_relation")
        except Exception as e:  # noqa: BLE001
            msg = str(e).split("\n")[0] if not hasattr(e, "errors") else "; ".join(
                f"{x['loc'][-1]}: {x['msg']}" for x in e.errors())
            errors.append({"row": i, "error": msg})
            continue
        if not body.dry_run:
            s = await create_student(student, ctx)
            await link_guardian(LinkIn(student_id=s["id"], guardian=guardian, relation=relation), ctx)
            created += 1
    await audit(ctx.user_id, "student.import", "student", None, ctx.school_id,
                {"rows": len(rows), "errors": len(errors), "dry_run": body.dry_run, "created": created})
    return {"rows": len(rows), "valid": len(rows) - len(errors), "errors": errors, "created": created,
            "dry_run": body.dry_run, "columns": CSV_COLUMNS}


# ---------------------------------------------------------------- teacher workspace
@router.get("/teacher/dashboard")
async def teacher_dashboard(ctx: Ctx = Depends(need("teacher.workspace"))):
    t = await db.teachers.find_one({"school_id": ctx.school_id, "user_id": ctx.user_id})
    if not t:
        return {"teacher": None, "sections": [], "total_students": 0}
    asg = await db.teacher_assignments.find({"school_id": ctx.school_id, "teacher_id": str(t["_id"])}).to_list(100)
    by_section: dict[str, dict] = {}
    for a in asg:
        sid = a["section_id"]
        sec = await db.sections.find_one({"_id": oid(sid)})
        if not sec:
            continue
        e = by_section.setdefault(sid, {"section_id": sid, "label": f"{sec['class_name']} - {sec['name']}",
                                        "class_name": sec["class_name"], "section_name": sec["name"],
                                        "subjects": [], "is_class_teacher": False,
                                        "students": await db.students.count_documents(
                                            {"school_id": ctx.school_id, "section_id": sid, "status": "active"})})
        if a.get("subject_id"):
            sub = await db.subjects.find_one({"_id": oid(a["subject_id"])})
            if sub:
                e["subjects"].append(sub["name"])
        e["is_class_teacher"] = e["is_class_teacher"] or a.get("is_class_teacher", False)
    sections = sorted(by_section.values(), key=lambda x: x["label"])
    return {"teacher": out(t), "sections": sections, "total_students": sum(s["students"] for s in sections)}


# ---------------------------------------------------------------- parent portal
async def _parent_links(ctx: Ctx) -> list[dict]:
    gids = [str(g["_id"]) for g in await db.guardians.find({"school_id": ctx.school_id, "user_id": ctx.user_id}).to_list(10)]
    return await db.guardian_links.find({"school_id": ctx.school_id, "guardian_id": {"$in": gids}, "verified": True}).to_list(20)


@router.get("/parent/children")
async def parent_children(ctx: Ctx = Depends(need("parent.portal"))):
    links = await _parent_links(ctx)
    items = []
    for link in links:
        s = await db.students.find_one({"_id": oid(link["student_id"]), "status": "active"})
        if s:
            items.append({**out(s), "relation": link["relation"]})
    return {"items": items}


@router.get("/parent/children/{student_id}")
async def parent_child(student_id: str, ctx: Ctx = Depends(need("parent.portal"))):
    links = await _parent_links(ctx)
    link = next((x for x in links if x["student_id"] == student_id), None)
    if not link:
        raise HTTPException(403, "You are not a verified guardian of this student")
    s = out(await get_owned("students", student_id, ctx.school_id))
    sec = await db.sections.find_one({"_id": oid(s["section_id"])})
    ct = None
    if sec and sec.get("class_teacher_id"):
        t = await db.teachers.find_one({"_id": oid(sec["class_teacher_id"])})
        ct = {"name": t["name"]} if t else None
    asg = await db.teacher_assignments.find({"school_id": ctx.school_id, "section_id": s["section_id"]}).to_list(50)
    subjects = []
    for a in asg:
        if a.get("subject_id"):
            sub = await db.subjects.find_one({"_id": oid(a["subject_id"])})
            t = await db.teachers.find_one({"_id": oid(a["teacher_id"])})
            if sub:
                subjects.append({"subject": sub["name"], "teacher": t["name"] if t else None})
    return {**s, "relation": link["relation"], "class_teacher": ct, "subjects": subjects}
