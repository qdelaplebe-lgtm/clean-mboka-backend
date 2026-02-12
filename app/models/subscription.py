from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime

from ..database import Base

class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    
    user_id = Column(Integer, ForeignKey("users.id"))
    user = relationship("User", back_populates="subscriptions")
    
    # Paiement
    amount = Column(Integer, default=100) # 100 (centimes) ou unité selon devise
    payment_method = Column(String, default="mobile_money") # Ex: Orange Money, M-Pesa
    
    # Période
    start_date = Column(DateTime, default=datetime.utcnow)
    end_date = Column(DateTime) # Date de fin de l'abonnement
    
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Subscription for User {self.user_id}>"
