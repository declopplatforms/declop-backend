import uuid
import json
import io

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from supabase_client import supabase
from s3 import upload_file, upload_profile_image
from deep_translator import GoogleTranslator

# ─── Size limits ──────────────────────────────────────────────────────────────
# Profile images are validated at 30 MB in the route handler before upload.
PROFILE_IMAGE_MAX_BYTES = 30 * 1024 * 1024   # 30 MB

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
        # ── 30 MB size guard ───────────────────────────────────────────────
        profile_bytes = await profile_image.read()
        if len(profile_bytes) > PROFILE_IMAGE_MAX_BYTES:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Profile image is too large "
                    f"({len(profile_bytes) / (1024*1024):.1f} MB). "
                    f"Maximum allowed size is 30 MB."
                ),
            )
        # Seek back to start so the uploader can read the stream
        profile_file_obj = io.BytesIO(profile_bytes)

        ext_prof = profile_image.filename.rsplit(".", 1)[-1] if "." in profile_image.filename else "jpg"
        filename_prof = f"{uuid.uuid4()}.{ext_prof}"
        try:
            # Use the dedicated high-quality profile-image uploader
            profile_image_url = upload_profile_image(
                profile_file_obj,
                filename_prof,
                profile_image.content_type or "image/jpeg",
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"S3 upload for profile image failed: {str(e)}")


    # ── Generate Translations ──────────────────────────────────────────────
    translations = {}
    target_langs = ["te", "hi", "ml", "kn", "ta"]
    
    def safe_translate(translator_obj, text):
        if not text:
            return text
        try:
            return translator_obj.translate(text)
        except Exception:
            return text

    try:
        for lang in target_langs:
            translator = GoogleTranslator(source='auto', target=lang)
            translations[lang] = {
                "title": safe_translate(translator, title),
                "description": safe_translate(translator, description),
                "by": safe_translate(translator, by),
                "segment": safe_translate(translator, segment),
                "cta": safe_translate(translator, cta),
                "resource1": safe_translate(translator, resource1),
                "resource2": safe_translate(translator, resource2),
                "resource3": safe_translate(translator, resource3),
            }
    except Exception as e:
        print(f"Warning: Translation setup failed: {str(e)}")

    # ── Save to Supabase ───────────────────────────────────────────────────
    payload = {
        "title":                title,
        "description":          description,
        "by":                   by,
        "image_url":            image_url,
        "translations":         translations,
        "profile_image":        profile_image_url,
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


# ─── CREATE STANDALONE AD ────────────────────────────────────────────────────
@app.post("/create-ad", status_code=201)
async def create_ad(
    ad_slides_data:  str                        = Form(...),   # JSON array
    ad_image_0:      Optional[UploadFile]       = File(None),
    ad_image_1:      Optional[UploadFile]       = File(None),
    ad_image_2:      Optional[UploadFile]       = File(None),
    ad_image_3:      Optional[UploadFile]       = File(None),
    scheduled_date:  Optional[str]              = Form(None),
):
    """
    Save one or more ad slides to the `ads` table, independent of any article.
    Each slide: { title, text, image_url (filled here) }
    """
    # ── Parse slides ───────────────────────────────────────────────────────
    try:
        parsed_slides = json.loads(ad_slides_data)
        if not isinstance(parsed_slides, list) or len(parsed_slides) == 0:
            raise ValueError("ad_slides_data must be a non-empty JSON array")
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid ad_slides_data: {str(e)}")

    # ── Upload images ──────────────────────────────────────────────────────
    ad_images = [ad_image_0, ad_image_1, ad_image_2, ad_image_3]
    for i, ad_image in enumerate(ad_images):
        if ad_image and i < len(parsed_slides):
            ext_ad = ad_image.filename.rsplit(".", 1)[-1] if "." in ad_image.filename else "jpg"
            filename_ad = f"ads/{uuid.uuid4()}.{ext_ad}"
            try:
                ad_url = upload_file(ad_image.file, filename_ad, ad_image.content_type or "image/jpeg")
                parsed_slides[i]["image_url"] = ad_url
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"S3 upload for ad_image_{i} failed: {str(e)}")

    # ── Save to Supabase ───────────────────────────────────────────────────
    payload = {
        "slides":         parsed_slides,
        "scheduled_date": scheduled_date or None,
    }
    try:
        result = (
            supabase
            .table("ads")
            .insert(payload)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database insert failed: {str(e)}")

    return {
        "message": "Ad created successfully 🎯",
        "ad":      result.data[0] if result.data else {},
    }


# ─── GET ALL ADS ──────────────────────────────────────────────────────────────
@app.get("/ads")
def get_ads():
    """Return all standalone ads ordered by newest first."""
    try:
        result = (
            supabase
            .table("ads")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query failed: {str(e)}")

    return {"ads": result.data}


# ─── DELETE AD ────────────────────────────────────────────────────────────────
@app.delete("/ads/{ad_id}")
def delete_ad(ad_id: str):
    try:
        supabase.table("ads").delete().eq("id", ad_id).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")

    return {"message": "Ad deleted successfully"}