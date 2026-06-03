from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from supabase_client import supabase
from s3 import upload_file
import uuid
import json
from deep_translator import GoogleTranslator

def translate_text(text: str, target_lang: str) -> str:
    try:
        if not text:
            return text
        return GoogleTranslator(source='auto', target=target_lang).translate(text)
    except Exception as e:
        print(f"Translation failed for {target_lang}: {e}")
        return text

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
        
        # ── Insert Translations ────────────────────────────────────────────────
        new_post = result.data[0] if result.data else None
        if new_post and new_post.get("id"):
            target_languages = ['te', 'hi', 'ml', 'kn', 'ta']
            translations = []
            for lang in target_languages:
                translated_title = translate_text(title, lang)
                translated_desc = translate_text(description, lang)
                translated_by = translate_text(by, lang)
                translated_segment = translate_text(segment, lang) if segment else None
                translated_cta = translate_text(cta, lang) if cta else None
                translated_res1 = translate_text(resource1, lang) if resource1 else None
                translated_res2 = translate_text(resource2, lang) if resource2 else None
                translated_res3 = translate_text(resource3, lang) if resource3 else None

                # translate arrays
                translated_regions = [translate_text(r, lang) for r in parsed_regions] if parsed_regions else []
                translated_languages = [translate_text(l, lang) for l in parsed_languages] if parsed_languages else []

                # translate ad_slides
                translated_ad_slides = []
                for slide in parsed_ad_slides:
                    translated_slide = dict(slide)
                    if translated_slide.get("title"):
                        translated_slide["title"] = translate_text(translated_slide["title"], lang)
                    if translated_slide.get("text"):
                        translated_slide["text"] = translate_text(translated_slide["text"], lang)
                    translated_ad_slides.append(translated_slide)

                translations.append({
                    "post_id": new_post["id"],
                    "language_code": lang,
                    "title": translated_title,
                    "description": translated_desc,
                    "by": translated_by,
                    "segment": translated_segment,
                    "cta": translated_cta,
                    "resource1": translated_res1,
                    "resource2": translated_res2,
                    "resource3": translated_res3,
                    "regions": translated_regions,
                    "languages": translated_languages,
                    "ad_slides": translated_ad_slides
                })
            
            if translations:
                try:
                    supabase.table("post_translations").insert(translations).execute()
                except Exception as e:
                    print(f"Failed to insert translations: {e}")
                    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database insert failed: {str(e)}")

    return {
        "message":   "Post created successfully 🎬",
        "image_url": image_url,
        "post":      new_post or {},
    }


# ─── GET ALL POSTS ────────────────────────────────────────────────────────────
@app.get("/posts")
def get_posts(lang: str = "en"):
    """Return all posts ordered by newest first, optionally translated."""
    try:
        result = (
            supabase
            .rpc("get_translated_posts", {"p_lang": lang})
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query failed: {str(e)}")

    return {"posts": result.data}


# ─── GET SINGLE POST ──────────────────────────────────────────────────────────
@app.get("/posts/{post_id}")
def get_post(post_id: str, lang: str = "en"):
    try:
        result = (
            supabase
            .rpc("get_translated_post", {"p_lang": lang, "p_post_id": post_id})
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="Post not found")
        post_data = result.data[0]
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=404, detail="Post not found")

    return {"post": post_data}


# ─── DELETE POST ──────────────────────────────────────────────────────────────
@app.delete("/posts/{post_id}")
def delete_post(post_id: str):
    try:
        supabase.table("posts").delete().eq("id", post_id).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")

    return {"message": "Post deleted successfully"}