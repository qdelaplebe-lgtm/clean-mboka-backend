from typing import Generator
from fastapi import Depends, HTTPException, status
from jose import JWTError, jwt
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)

from .. import crud, models
from ..core.security import oauth2_scheme
from ..core.config import settings
from ..database import get_db

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        identifier: str = payload.get("sub")
        
        # Debug logging
        logger.info(f"JWT payload: {payload}")
        
        if identifier is None:
            logger.error("No 'sub' claim in JWT token")
            raise credentials_exception
            
        # Essayer par téléphone
        user = crud.get_user_by_phone(db, phone=identifier)
        
        # Si non trouvé, essayer par email
        if user is None:
            logger.info(f"No user found with phone {identifier}, trying email")
            user = crud.get_user_by_email(db, email=identifier)
            
        if user:
            logger.info(f"User authenticated: {user.id} - {user.email}")
        else:
            logger.error(f"No user found with identifier: {identifier}")
            
    except JWTError as e:
        logger.error(f"JWT Error: {e}")
        raise credentials_exception
    except Exception as e:
        logger.error(f"Unexpected auth error: {e}")
        raise credentials_exception

    if user is None:
        raise credentials_exception
    
    return user
