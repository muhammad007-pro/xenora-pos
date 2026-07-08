from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
import os
import uuid
from datetime import datetime
from typing import Optional

from database import get_db
from models import User
from deps import get_current_user
from schemas import MessageResponse
from config import settings

router = APIRouter()

ALLOWED_EXTENSIONS = {
    'image': ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg'],
    'document': ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.txt'],
    'audio': ['.mp3', '.wav', '.ogg']
}

@router.post("/image")
async def upload_image(
    file: UploadFile = File(...),
    folder: str = "general",
    current_user: User = Depends(get_current_user)
):
    """Rasm yuklash"""
    return await save_uploaded_file(file, folder, 'image')

@router.post("/document")
async def upload_document(
    file: UploadFile = File(...),
    folder: str = "documents",
    current_user: User = Depends(get_current_user)
):
    """Hujjat yuklash"""
    return await save_uploaded_file(file, folder, 'document')

@router.post("/multiple")
async def upload_multiple(
    files: list[UploadFile] = File(...),
    folder: str = "general",
    current_user: User = Depends(get_current_user)
):
    """Bir nechta fayl yuklash"""
    results = []
    
    for file in files:
        result = await save_uploaded_file(file, folder)
        results.append(result)
    
    return {"files": results}

async def save_uploaded_file(
    file: UploadFile,
    folder: str = "general",
    file_type: str = 'image'
) -> dict:
    """Faylni saqlash"""
    
    # Fayl kengaytmasini tekshirish
    file_ext = os.path.splitext(file.filename)[1].lower()
    
    if file_type == 'image' and file_ext not in ALLOWED_EXTENSIONS['image']:
        raise HTTPException(status_code=400, detail="Ruxsat etilmagan rasm formati")
    
    # Fayl nomini yaratish
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = uuid.uuid4().hex[:8]
    filename = f"{timestamp}_{unique_id}{file_ext}"
    
    # Papkani yaratish
    upload_dir = os.path.join(settings.UPLOAD_DIR, folder)
    os.makedirs(upload_dir, exist_ok=True)
    
    # Faylni saqlash
    file_path = os.path.join(upload_dir, filename)
    
    content = await file.read()
    
    # Fayl hajmini tekshirish
    if len(content) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="Fayl hajmi juda katta")
    
    with open(file_path, "wb") as f:
        f.write(content)
    
    # URL yaratish
    file_url = f"/uploads/{folder}/{filename}"
    
    return {
        "filename": filename,
        "original_name": file.filename,
        "url": file_url,
        "size": len(content),
        "content_type": file.content_type
    }

@router.delete("/{folder}/{filename}")
async def delete_file(
    folder: str,
    filename: str,
    current_user: User = Depends(get_current_user)
):
    """Faylni o'chirish"""
    file_path = os.path.join(settings.UPLOAD_DIR, folder, filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Fayl topilmadi")
    
    try:
        os.remove(file_path)
        return MessageResponse(message="Fayl o'chirildi")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Faylni o'chirishda xatolik: {str(e)}")

@router.get("/list/{folder}")
async def list_files(
    folder: str,
    current_user: User = Depends(get_current_user)
):
    """Papkadagi fayllar ro'yxati"""
    folder_path = os.path.join(settings.UPLOAD_DIR, folder)
    
    if not os.path.exists(folder_path):
        return []
    
    files = []
    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        if os.path.isfile(file_path):
            stat = os.stat(file_path)
            files.append({
                "name": filename,
                "url": f"/uploads/{folder}/{filename}",
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
            })
    
    return sorted(files, key=lambda x: x["modified"], reverse=True)