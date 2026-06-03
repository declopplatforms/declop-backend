from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from supabase_client import supabase
from s3 import upload_file
import uuid
import json

app = FastAPI(title="Declop Movie News API", version="2.0.0")

# ─── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── HEALTH CHECK ─────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "Declop Movie News API is running 🎬",
        "version": "2.0.0",
        "endpoints": {
            "health":      "GET  /",
            "list_posts":  "GET  /posts",
            "get_post":    "GET  /posts/{id}",
            "create_post": "POST /create-post",
            "delete_post": "DELETE /posts/{id}",
        }
    }


# ─── CREATE POST ──────────────────────────────────────────────────────────────
@app.post("/create-post", status_code=201)
async def create_post(
    title:                str          = Form(...),
    description:          str          = Form(...),
    by:                   str          = Form(...),
    resource1:            str          = Form(...),
    image:                UploadFile   = File(...),
    profile_image:        Optional[UploadFile] = File(None),
    ad_slides_data:       Optional[str] = Form(None),
    ad_image_0:           Optional[UploadFile] = File(None),
    ad_image_1:           Optional[UploadFile] = File(None),
    ad_image_2:           Optional[UploadFile] = File(None),
    ad_image_3:           Optional[UploadFile] = File(None),
    regions:              Optional[str] = Form(None),    # JSON array string
    languages:            Optional[str] = Form(None),    # JSON array string
    segment:              Optional[str] = Form(None),
    cta:                  Optional[str] = Form(None),
    cta_link:             Optional[str] = Form(None),
    resource2:            Optional[str] = Form(None),
    resource3:            Optional[str] = Form(None),

    scheduled_date:       Optional[str] = Form(None),
):
    # ── Parse JSON arrays ──────────────────────────────────────────────────
    def safe_parse(value, field_name):
        if not value:
            return []
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else [parsed]
        except (json.JSONDecodeError, TypeError):
            return [value]

    parsed_regions   = safe_parse(regions, "regions")
    parsed_languages = safe_parse(languages, "languages")

    # ── Upload image to S3 ─────────────────────────────────────────────────
    ext      = image.filename.rsplit(".", 1)[-1] if "." in image.filename else "jpg"
    filename = f"{uuid.uuid4()}.{ext}"

    try:
        image_url = upload_file(image.file, filename, image.content_type or "image/jpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"S3 upload failed: {str(e)}")

    profile_image_url = None
    if profile_image:
        ext_prof = profile_image.filename.rsplit(".", 1)[-1] if "." in profile_image.filename else "jpg"
        filename_prof = f"{uuid.uuid4()}.{ext_prof}"
        try:
            profile_image_url = upload_file(profile_image.file, filename_prof, profile_image.content_type or "image/jpeg")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"S3 upload for profile image failed: {str(e)}")

    # ── Parse and Upload Ad Slides ─────────────────────────────────────────
    parsed_ad_slides = []
    if ad_slides_data:
        try:
            parsed_ad_slides = json.loads(ad_slides_data)
        except json.JSONDecodeError:
            pass

    ad_images = [ad_image_0, ad_image_1, ad_image_2, ad_image_3]
    for i, ad_image in enumerate(ad_images):
        if ad_image and i < len(parsed_ad_slides):
            ext_ad = ad_image.filename.rsplit(".", 1)[-1] if "." in ad_image.filename else "jpg"
            filename_ad = f"{uuid.uuid4()}.{ext_ad}"
            try:
                ad_url = upload_file(ad_image.file, filename_ad, ad_image.content_type or "image/jpeg")
                parsed_ad_slides[i]["image_url"] = ad_url
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"S3 upload for ad_image_{i} failed: {str(e)}")

    # ── Save to Supabase ───────────────────────────────────────────────────
    payload = {
        "title":                title,
        "description":          description,
        "by":                   by,
        "image_url":            image_url,
        "profile_image":        profile_image_url,
        "ad_slides":            parsed_ad_slides,
        "regions":              parsed_regions,
        "languages":            parsed_languages,
        "segment":              segment or None,
        "cta":                  cta or None,
        "cta_link":             cta_link or None,
        "resource1":            resource1,
        "resource2":            resource2 or None,
        "resource3":            resource3 or None,

        "scheduled_date":       scheduled_date or None,
    }

    try:
        result = (
            supabase
            .table("posts")
            .insert(payload)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database insert failed: {str(e)}")

    return {
        "message":   "Post created successfully 🎬",
        "image_url": image_url,
        "post":      result.data[0] if result.data else {},
    }


# ─── GET ALL POSTS ────────────────────────────────────────────────────────────
@app.get("/posts")
def get_posts():
    """Return all posts ordered by newest first."""
    try:
        result = (
            supabase
            .table("posts")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query failed: {str(e)}")

    return {"posts": result.data}


# ─── GET SINGLE POST ──────────────────────────────────────────────────────────
@app.get("/posts/{post_id}")
def get_post(post_id: str):
    try:
        result = (
            supabase
            .table("posts")
            .select("*")
            .eq("id", post_id)
            .single()
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail="Post not found")

    return {"post": result.data}


# ─── DELETE POST ──────────────────────────────────────────────────────────────
@app.delete("/posts/{post_id}")
def delete_post(post_id: str):
    try:
        supabase.table("posts").delete().eq("id", post_id).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")

    return {"message": "Post deleted successfully"}