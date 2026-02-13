import cloudinary
from app.core.config import settings

cloudinary.config(
    cloudinary_url=settings.CLOUDINARY_URL,
    secure=True
)
