# app/schemas/token.py
from pydantic import BaseModel, Field
from typing import Optional

class Token(BaseModel):
    """
    Retourné après une connexion réussie.
    L'application frontend stockera ce 'access_token'.
    """
    access_token: str
    token_type: str = "bearer"
    
    class Config:
        json_schema_extra = {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer"
            }
        }

class LoginRequest(BaseModel):
    """
    Requête de connexion - Utilisé par le frontend.
    """
    username: str = Field(..., example="+243810000001", description="Numéro de téléphone")
    password: str = Field(..., example="Password123", description="Mot de passe")
    
    class Config:
        json_schema_extra = {
            "example": {
                "username": "+243810000001",
                "password": "Password123"
            }
        }

class TokenData(BaseModel):
    """
    Données extraites du token JWT (usage interne).
    """
    username: Optional[str] = None
    user_id: Optional[int] = None
    role: Optional[str] = None
    
    class Config:
        from_attributes = True

class RefreshToken(BaseModel):
    """
    Pour rafraîchir un token expiré.
    """
    refresh_token: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
            }
        }

class TokenResponse(BaseModel):
    """
    Réponse complète avec token et informations utilisateur.
    """
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(3600, description="Durée de validité en secondes")
    user_id: int
    role: str
    full_name: str
    commune: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 3600,
                "user_id": 1,
                "role": "citoyen",
                "full_name": "Jean Mutombo",
                "commune": "Lemba"
            }
        }
