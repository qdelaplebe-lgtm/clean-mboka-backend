# app/services/file_service.py
"""
Service de gestion des fichiers pour Clean Mboka.
Gère l'upload, validation et suppression des photos de profil.
"""
import os
import uuid
import shutil
from fastapi import UploadFile, HTTPException
from typing import Optional, Tuple
import aiofiles
from datetime import datetime
from pathlib import Path

class FileService:
    """Service de gestion des fichiers"""
    
    def __init__(self):
        self.profile_pictures_dir = "static/profile_pictures"
        self.reports_dir = "uploads"  # Dossier pour les photos de signalements
        
        # Extensions autorisées pour les photos de profil
        self.allowed_extensions = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
        
        # Taille maximale des fichiers (5MB)
        self.max_size_mb = 5
        self.max_size_bytes = self.max_size_mb * 1024 * 1024
        
        # Créer les dossiers s'ils n'existent pas
        self._create_directories()
    
    def _create_directories(self):
        """Créer les dossiers nécessaires"""
        os.makedirs(self.profile_pictures_dir, exist_ok=True)
        os.makedirs(self.reports_dir, exist_ok=True)
    
    def validate_profile_picture(self, file: UploadFile) -> Tuple[bool, str]:
        """
        Valider une photo de profil.
        
        Args:
            file: Fichier uploadé via FastAPI
            
        Returns:
            Tuple[bool, str]: (is_valid, error_message)
        """
        # Vérifier si un fichier a été fourni
        if not file or file.filename == "":
            return False, "Aucun fichier sélectionné"
        
        # Vérifier la taille du fichier
        try:
            # Lire la taille du fichier
            file.file.seek(0, 2)  # Aller à la fin
            file_size = file.file.tell()
            file.file.seek(0)  # Revenir au début
            
            if file_size > self.max_size_bytes:
                return False, f"Fichier trop volumineux. Maximum: {self.max_size_mb}MB"
            
            if file_size == 0:
                return False, "Le fichier est vide"
                
        except Exception as e:
            return False, f"Erreur de lecture du fichier: {str(e)}"
        
        # Vérifier l'extension
        filename = file.filename or ""
        file_ext = Path(filename).suffix.lower()
        
        if file_ext not in self.allowed_extensions:
            allowed_str = ", ".join(self.allowed_extensions)
            return False, f"Type de fichier non autorisé. Utilisez: {allowed_str}"
        
        # Vérifier le type MIME
        content_type = file.content_type or ""
        if not content_type.startswith("image/"):
            return False, "Le fichier doit être une image"
        
        return True, ""
    
    def generate_profile_filename(self, user_id: int, original_filename: str) -> str:
        """
        Générer un nom de fichier unique pour une photo de profil.
        
        Args:
            user_id: ID de l'utilisateur
            original_filename: Nom original du fichier
            
        Returns:
            str: Nom de fichier unique
        """
        # Extraire l'extension
        file_ext = Path(original_filename).suffix.lower()
        
        # Générer un nom unique avec timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = uuid.uuid4().hex[:8]
        
        # Format: user_{id}_{timestamp}_{unique_id}{ext}
        return f"user_{user_id}_{timestamp}_{unique_id}{file_ext}"
    
    async def save_profile_picture(self, file: UploadFile, user_id: int) -> str:
        """
        Sauvegarder une photo de profil sur le disque.
        
        Args:
            file: Fichier uploadé
            user_id: ID de l'utilisateur
            
        Returns:
            str: Chemin relatif vers le fichier sauvegardé
        """
        # Valider le fichier
        is_valid, error_msg = self.validate_profile_picture(file)
        if not is_valid:
            raise ValueError(error_msg)
        
        # Générer un nom de fichier unique
        filename = self.generate_profile_filename(user_id, file.filename)
        filepath = os.path.join(self.profile_pictures_dir, filename)
        
        try:
            # Sauvegarder le fichier
            async with aiofiles.open(filepath, 'wb') as out_file:
                # Lire par chunks pour gérer les gros fichiers
                while True:
                    chunk = await file.read(8192)  # 8KB chunks
                    if not chunk:
                        break
                    await out_file.write(chunk)
            
            # Retourner le chemin relatif pour l'URL
            return f"/static/profile_pictures/{filename}"
            
        except Exception as e:
            # Nettoyer en cas d'erreur
            if os.path.exists(filepath):
                os.remove(filepath)
            raise Exception(f"Erreur lors de la sauvegarde du fichier: {str(e)}")
    
    def delete_profile_picture(self, picture_url: Optional[str]) -> bool:
        """
        Supprimer une photo de profil du disque.
        
        Args:
            picture_url: URL de la photo à supprimer
            
        Returns:
            bool: True si supprimé, False sinon
        """
        if not picture_url:
            return False
        
        try:
            # Extraire le nom de fichier de l'URL
            # Format attendu: /static/profile_pictures/filename.jpg
            if picture_url.startswith("/static/profile_pictures/"):
                filename = picture_url.split("/")[-1]
                filepath = os.path.join(self.profile_pictures_dir, filename)
                
                # Vérifier que le fichier existe
                if os.path.exists(filepath):
                    os.remove(filepath)
                    return True
            
            # Si c'est un chemin complet avec l'IP
            elif "profile_pictures" in picture_url:
                # Extraire le nom de fichier de l'URL complète
                # Ex: http://16.171.198.83:8000/static/profile_pictures/filename.jpg
                parts = picture_url.split("profile_pictures/")
                if len(parts) > 1:
                    filename = parts[-1]
                    filepath = os.path.join(self.profile_pictures_dir, filename)
                    
                    if os.path.exists(filepath):
                        os.remove(filepath)
                        return True
            
            return False
            
        except Exception as e:
            print(f"Erreur lors de la suppression de la photo: {str(e)}")
            return False
    
    def get_profile_picture_path(self, picture_url: Optional[str]) -> Optional[str]:
        """
        Obtenir le chemin physique d'une photo de profil à partir de son URL.
        
        Args:
            picture_url: URL de la photo
            
        Returns:
            Optional[str]: Chemin physique ou None
        """
        if not picture_url:
            return None
        
        try:
            if picture_url.startswith("/static/profile_pictures/"):
                filename = picture_url.split("/")[-1]
                return os.path.join(self.profile_pictures_dir, filename)
            
            elif "profile_pictures" in picture_url:
                parts = picture_url.split("profile_pictures/")
                if len(parts) > 1:
                    filename = parts[-1]
                    return os.path.join(self.profile_pictures_dir, filename)
            
            return None
            
        except Exception:
            return None
    
    def list_user_profile_pictures(self, user_id: int) -> list:
        """
        Lister toutes les photos de profil d'un utilisateur.
        Utile pour le nettoyage des anciennes photos.
        
        Args:
            user_id: ID de l'utilisateur
            
        Returns:
            list: Liste des chemins de fichiers
        """
        try:
            user_files = []
            pattern = f"user_{user_id}_*"
            
            for filename in os.listdir(self.profile_pictures_dir):
                if filename.startswith(f"user_{user_id}_"):
                    filepath = os.path.join(self.profile_pictures_dir, filename)
                    user_files.append(filepath)
            
            return user_files
            
        except Exception:
            return []
    
    def cleanup_old_profile_pictures(self, user_id: int, keep_latest: int = 3):
        """
        Nettoyer les anciennes photos de profil, garder seulement les plus récentes.
        
        Args:
            user_id: ID de l'utilisateur
            keep_latest: Nombre de photos récentes à conserver
        """
        try:
            user_files = self.list_user_profile_pictures(user_id)
            
            if len(user_files) <= keep_latest:
                return
            
            # Trier par date de modification (plus récent d'abord)
            user_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            
            # Supprimer les anciennes
            for old_file in user_files[keep_latest:]:
                try:
                    os.remove(old_file)
                except Exception:
                    pass
                    
        except Exception as e:
            print(f"Erreur lors du nettoyage des anciennes photos: {str(e)}")
    
    def get_file_info(self, picture_url: Optional[str]) -> Optional[dict]:
        """
        Obtenir des informations sur un fichier.
        
        Args:
            picture_url: URL de la photo
            
        Returns:
            Optional[dict]: Informations ou None
        """
        filepath = self.get_profile_picture_path(picture_url)
        
        if not filepath or not os.path.exists(filepath):
            return None
        
        try:
            stat = os.stat(filepath)
            return {
                "path": filepath,
                "size_bytes": stat.st_size,
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "created": datetime.fromtimestamp(stat.st_ctime),
                "modified": datetime.fromtimestamp(stat.st_mtime),
                "filename": os.path.basename(filepath)
            }
        except Exception:
            return None
    
    def compress_image(self, input_path: str, output_path: str, quality: int = 85):
        """
        Compresser une image (si PIL est disponible).
        
        Args:
            input_path: Chemin de l'image source
            output_path: Chemin de l'image compressée
            quality: Qualité de compression (1-100)
        """
        try:
            # Vérifier si PIL/Pillow est disponible
            from PIL import Image
            
            with Image.open(input_path) as img:
                # Convertir en RGB si nécessaire
                if img.mode in ('RGBA', 'LA', 'P'):
                    rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                    rgb_img.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                    img = rgb_img
                
                # Sauvegarder avec compression
                img.save(output_path, 'JPEG' if output_path.lower().endswith('.jpg') else 'PNG', 
                        quality=quality, optimize=True)
                
            return True
            
        except ImportError:
            print("PIL/Pillow non installé. La compression n'est pas disponible.")
            return False
            
        except Exception as e:
            print(f"Erreur lors de la compression: {str(e)}")
            return False
    
    def create_thumbnail(self, input_path: str, output_path: str, size: tuple = (150, 150)):
        """
        Créer une miniature d'une image.
        
        Args:
            input_path: Chemin de l'image source
            output_path: Chemin de la miniature
            size: Dimensions (largeur, hauteur)
        """
        try:
            from PIL import Image
            
            with Image.open(input_path) as img:
                # Créer la miniature
                img.thumbnail(size)
                img.save(output_path)
                
            return True
            
        except ImportError:
            print("PIL/Pillow non installé. Les miniatures ne sont pas disponibles.")
            return False
            
        except Exception as e:
            print(f"Erreur lors de la création de la miniature: {str(e)}")
            return False

# Instance globale du service
file_service = FileService()
