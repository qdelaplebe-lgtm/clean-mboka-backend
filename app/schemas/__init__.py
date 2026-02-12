# app/schemas/__init__.py
from .user import (
    UserBase,
    UserCreate,
    User,
    UserResponse,
    UserInDB,
    UserLogin,
    Token,
    UserStats,
    UserUpdate,
    ProfilePictureUpdate,
    PasswordChange,
    PasswordResetRequest,
    PasswordReset,
    EmailVerification,
    AgentCreate,
    RoleAssignment,
    ZoneAssignment,
    PointsUpdate,
    UserSimple,
    PaginatedUserResponse,
    UserExtendedStats,
    # ========== NOUVEAUX SCHÉMAS POINTS ==========
    UserPointsResponse,
    RewardThreshold,
    NextReward,
    PointsHistoryEntry
)

from .report import (
    ReportCreate,
    ReportStatusUpdate,
    ReportUpdate,
    ReportList,
    ReportResponse,
    ReportDetail,
    ReportStatistics,
    ReportFilter,
    PaginatedReportResponse,
    ReportStatusEnum,
    MyReport,
    UserSimple as ReportUserSimple,
    # --- SCHÉMAS CONFIRMATION PHOTO ---
    ReportPhotoSubmit,
    CitizenConfirmation,
    CleanupStatusResponse,
    ConfirmationReport,
    # ========== NOUVEAU SCHÉMA POIDS ==========
    ReportWeightUpdate,
    # ========== NOUVEAUX SCHÉMAS STATISTIQUES ==========
    ReportCommuneStats,
    ReportMonthlyStats,
    CollectorPerformanceStats,
    CitizenImpactStats
)

from .subscription import (
    SubscriptionBase,
    SubscriptionCreate,
    SubscriptionUpdate,
    SubscriptionResponse,
    SubscriptionDetail,
    PaymentInitiation,
    PaymentConfirmation,
    SubscriptionStats,
    UserSubscriptionStatus,
    SubscriptionStatusEnum
)

# ✅ CORRECTION: Import depuis token.py
from .token import (
    Token as TokenSchema,  # Renommage pour éviter conflit avec User.Token
    LoginRequest,
    TokenData,
    RefreshToken,
    TokenResponse
)

__all__ = [
    # User schemas
    "UserBase", "UserCreate", "User", "UserResponse",
    "UserInDB", "UserLogin", "UserUpdate", "UserStats",
    "ProfilePictureUpdate", "PasswordChange", "PasswordResetRequest",
    "PasswordReset", "EmailVerification", "AgentCreate", "RoleAssignment",
    "ZoneAssignment", "PointsUpdate", "UserSimple", "PaginatedUserResponse",
    "UserExtendedStats",
    "UserPointsResponse", "RewardThreshold", "NextReward", "PointsHistoryEntry",

    # Report schemas
    "ReportCreate", "ReportStatusUpdate", "ReportUpdate",
    "ReportList", "ReportResponse", "ReportDetail",
    "ReportStatistics", "ReportFilter", "PaginatedReportResponse",
    "ReportStatusEnum", "MyReport", "ReportUserSimple",
    "ReportPhotoSubmit", "CitizenConfirmation",
    "CleanupStatusResponse", "ConfirmationReport",
    "ReportWeightUpdate",
    "ReportCommuneStats", "ReportMonthlyStats",
    "CollectorPerformanceStats", "CitizenImpactStats",

    # Subscription schemas
    "SubscriptionBase", "SubscriptionCreate", "SubscriptionUpdate",
    "SubscriptionResponse", "SubscriptionDetail",
    "PaymentInitiation", "PaymentConfirmation",
    "SubscriptionStats", "UserSubscriptionStatus", "SubscriptionStatusEnum",

    # Token schemas
    "TokenSchema",  # ✅ Utiliser TokenSchema pour éviter conflit
    "LoginRequest",  # ✅ MAINTENANT DISPONIBLE
    "TokenData",
    "RefreshToken",
    "TokenResponse"
]
