"""One-time download grants (native in-app browser path). Web uses header-authenticated fetches instead."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

import storage
from core import PERMISSIONS, Ctx, db, oid, school_ctx
from file_access import active_membership, authorize_file, consume_grant, issue_grant

router = APIRouter()
NO_STORE = {"Cache-Control": "private, no-store, max-age=0", "Pragma": "no-cache", "Expires": "0",
            "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"}


@router.post("/files/{file_id}/download-grant")
async def file_grant(file_id: str, ctx: Ctx = Depends(school_ctx)):
    f = await db.files.find_one({"_id": oid(file_id), "school_id": ctx.school_id, "is_deleted": False})
    if not f:
        raise HTTPException(404, "File not found")
    await authorize_file(ctx.user_id, f)
    return await issue_grant(ctx.user_id, ctx.school_id, "file", {"file_id": file_id})


@router.get("/downloads/{token}")
async def download(token: str):
    g = await consume_grant(token)
    uid = str(g["user"]["_id"])
    # re-authorise at use time so revocations between grant and click still apply
    if g["kind"] == "file":
        f = await db.files.find_one({"_id": oid(g["ref"]["file_id"]), "school_id": g["school_id"], "is_deleted": False})
        if not f:
            raise HTTPException(404, "File not found")
        await authorize_file(uid, f)
        data, ctype = await run_in_threadpool(storage.get_object, f["storage_path"])
        name = (f.get("original_name") or "attachment").replace('"', "")
        return Response(content=data, media_type=f.get("content_type") or ctype,
                        headers={**NO_STORE, "Content-Disposition": f'inline; filename="{name}"'})
    if g["kind"] == "report_card":
        m = await active_membership(uid, g["school_id"])
        if not m:
            raise HTTPException(403, "Not permitted")
        from routes_exams import pdf_response, render_report_card
        ctx = Ctx(user=g["user"], user_id=uid, school_id=g["school_id"], role=m["role"], perms=PERMISSIONS.get(m["role"], set()))
        pdf, name = await render_report_card(ctx, g["ref"]["exam_id"], g["ref"]["student_id"])
        resp = pdf_response(pdf, name)
        resp.headers["Content-Disposition"] = f'inline; filename="{name}"'
        return resp
    raise HTTPException(404, "Unknown download")
