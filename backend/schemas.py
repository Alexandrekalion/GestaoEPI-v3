from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List
from datetime import datetime, timezone
from enum import Enum
from bson import ObjectId
import re

class PyObjectId(str):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v, info=None):
        if isinstance(v, ObjectId):
            return str(v)
        if isinstance(v, str) and ObjectId.is_valid(v):
            return v
        raise ValueError("Invalid ObjectId")

# Novos perfis de acesso
class UserRole(str, Enum):
    ADMIN = "admin"              # Administrador - acesso total
    GESTOR = "gestor"            # Gestor - acesso operacional total
    RH = "rh"                    # RH - colaboradores, empresas, usuários
    SEGURANCA_TRABALHO = "seguranca_trabalho"  # Seg. Trabalho - EPIs, fornecedores
    ALMOXARIFADO = "almoxarifado"  # Almoxarifado - entregas, movimentação

class EmployeeStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"

class StockMovementType(str, Enum):
    PURCHASE = "purchase"
    DELIVERY = "delivery"
    RETURN = "return"
    ADJUSTMENT = "adjustment"
    DISCARD = "discard"

class ItemCondition(str, Enum):
    NEW = "new"
    USED = "used"
    DAMAGED = "damaged"

# ===================== AUTH =====================

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    must_change_password: bool
    password_expired: bool = False
    role: UserRole

class LoginRequest(BaseModel):
    username: str
    password: str

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str
    
    @field_validator('new_password')
    @classmethod
    def validate_password_complexity(cls, v):
        if len(v) < 8:
            raise ValueError('A senha deve ter no mínimo 8 caracteres')
        if not re.search(r'[A-Z]', v):
            raise ValueError('A senha deve conter pelo menos uma letra maiúscula')
        if not re.search(r'[a-z]', v):
            raise ValueError('A senha deve conter pelo menos uma letra minúscula')
        if not re.search(r'\d', v):
            raise ValueError('A senha deve conter pelo menos um número')
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError('A senha deve conter pelo menos um caractere especial (!@#$%^&*)')
        return v

# ===================== USER =====================

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    role: UserRole = UserRole.ALMOXARIFADO
    employee_id: Optional[str] = None
    
    @field_validator('password')
    @classmethod
    def validate_password_complexity(cls, v):
        if len(v) < 8:
            raise ValueError('A senha deve ter no mínimo 8 caracteres')
        if not re.search(r'[A-Z]', v):
            raise ValueError('A senha deve conter pelo menos uma letra maiúscula')
        if not re.search(r'[a-z]', v):
            raise ValueError('A senha deve conter pelo menos uma letra minúscula')
        if not re.search(r'\d', v):
            raise ValueError('A senha deve conter pelo menos um número')
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError('A senha deve conter pelo menos um caractere especial (!@#$%^&*)')
        return v

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None

class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    role: UserRole
    is_active: bool
    must_change_password: bool
    password_changed_at: Optional[datetime] = None
    employee_id: Optional[str] = None
    created_at: datetime

class UserInDB(BaseModel):
    username: str
    email: str
    hashed_password: str
    role: UserRole = UserRole.ALMOXARIFADO
    is_active: bool = True
    must_change_password: bool = True
    password_changed_at: Optional[datetime] = None
    employee_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# ===================== COMPANY =====================

class CompanyCreate(BaseModel):
    legal_name: str
    trade_name: Optional[str] = None
    cnpj: str
    address: Optional[str] = None
    contact_person: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    notes: Optional[str] = None

class CompanyUpdate(BaseModel):
    legal_name: Optional[str] = None
    trade_name: Optional[str] = None
    address: Optional[str] = None
    contact_person: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    notes: Optional[str] = None

class CompanyResponse(BaseModel):
    id: str
    legal_name: str
    trade_name: Optional[str] = None
    cnpj: str
    address: Optional[str] = None
    contact_person: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime

# ===================== EMPLOYEE =====================

class EmployeeCreate(BaseModel):
    full_name: str
    cpf: str
    rg: Optional[str] = None
    birth_date: Optional[datetime] = None
    address: Optional[str] = None
    registration_number: str  # Matrícula obrigatória
    company_id: str  # Empresa obrigatória
    department: Optional[str] = None
    position: Optional[str] = None
    status: EmployeeStatus = EmployeeStatus.ACTIVE
    facial_consent: bool = False
    notes: Optional[str] = None

class EmployeeUpdate(BaseModel):
    full_name: Optional[str] = None
    rg: Optional[str] = None
    birth_date: Optional[datetime] = None
    address: Optional[str] = None
    registration_number: Optional[str] = None
    company_id: Optional[str] = None
    department: Optional[str] = None
    position: Optional[str] = None
    status: Optional[EmployeeStatus] = None
    facial_consent: Optional[bool] = None
    notes: Optional[str] = None

class EmployeeResponse(BaseModel):
    id: str
    full_name: str
    cpf: str
    rg: Optional[str] = None
    birth_date: Optional[datetime] = None
    address: Optional[str] = None
    registration_number: Optional[str] = None
    company_id: Optional[str] = None
    department: Optional[str] = None
    position: Optional[str] = None
    status: EmployeeStatus
    photo_path: Optional[str] = None
    facial_consent: bool
    notes: Optional[str] = None
    created_at: datetime

# Resposta para perfis que não podem ver dados sensíveis
class EmployeePublicResponse(BaseModel):
    id: str
    full_name: str
    registration_number: Optional[str] = None
    company_id: Optional[str] = None
    department: Optional[str] = None
    position: Optional[str] = None
    status: EmployeeStatus
    photo_path: Optional[str] = None
    created_at: datetime

# ===================== SUPPLIER =====================

class SupplierCreate(BaseModel):
    name: str
    cnpj: str  # CNPJ obrigatório
    contact: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None

class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    cnpj: Optional[str] = None
    contact: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None

class SupplierResponse(BaseModel):
    id: str
    name: str
    cnpj: Optional[str] = None
    contact: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    created_at: datetime

# ===================== EPI =====================

class EPICreate(BaseModel):
    name: str
    type_category: str
    brand: Optional[str] = None
    model: Optional[str] = None
    color: Optional[str] = None
    size: Optional[str] = None
    material: Optional[str] = None
    ca_number: str
    ca_validity: Optional[datetime] = None
    technical_standard: Optional[str] = None
    supplier_id: Optional[str] = None
    invoice_number: Optional[str] = None
    purchase_date: Optional[datetime] = None
    quantity_purchased: int = 0
    unit_price: Optional[float] = None
    total_price: Optional[float] = None
    cost_center: Optional[str] = None
    cid_field: Optional[str] = None
    internal_code: Optional[str] = None
    batch: Optional[str] = None
    qr_code: Optional[str] = None
    storage_location: Optional[str] = None
    estimated_life: Optional[int] = None
    validity_date: Optional[datetime] = None
    current_stock: int = 0
    min_stock: int = 0
    max_stock: Optional[int] = None

class EPIUpdate(BaseModel):
    name: Optional[str] = None
    type_category: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    color: Optional[str] = None
    size: Optional[str] = None
    material: Optional[str] = None
    ca_number: Optional[str] = None
    ca_validity: Optional[datetime] = None
    technical_standard: Optional[str] = None
    supplier_id: Optional[str] = None
    invoice_number: Optional[str] = None
    purchase_date: Optional[datetime] = None
    quantity_purchased: Optional[int] = None
    unit_price: Optional[float] = None
    total_price: Optional[float] = None
    cost_center: Optional[str] = None
    cid_field: Optional[str] = None
    internal_code: Optional[str] = None
    batch: Optional[str] = None
    qr_code: Optional[str] = None
    storage_location: Optional[str] = None
    estimated_life: Optional[int] = None
    validity_date: Optional[datetime] = None
    current_stock: Optional[int] = None
    min_stock: Optional[int] = None
    max_stock: Optional[int] = None

class EPIResponse(BaseModel):
    id: str
    name: str
    type_category: str
    brand: Optional[str] = None
    model: Optional[str] = None
    color: Optional[str] = None
    size: Optional[str] = None
    material: Optional[str] = None
    ca_number: str
    ca_validity: Optional[datetime] = None
    technical_standard: Optional[str] = None
    supplier_id: Optional[str] = None
    invoice_number: Optional[str] = None
    purchase_date: Optional[datetime] = None
    quantity_purchased: int
    unit_price: Optional[float] = None
    total_price: Optional[float] = None
    cost_center: Optional[str] = None
    cid_field: Optional[str] = None
    internal_code: Optional[str] = None
    batch: Optional[str] = None
    qr_code: Optional[str] = None
    storage_location: Optional[str] = None
    estimated_life: Optional[int] = None
    validity_date: Optional[datetime] = None
    current_stock: int
    min_stock: int
    max_stock: Optional[int] = None
    stock_status: Optional[str] = None  # 'ok', 'low', 'out'
    validity_status: Optional[str] = None  # 'ok', 'expiring', 'expired'
    created_at: datetime

# ===================== KIT =====================

class KitItemInput(BaseModel):
    epi_id: Optional[str] = None
    quantity: int = 1

class KitCreate(BaseModel):
    name: str
    description: Optional[str] = None
    sector: Optional[str] = None  # Setor: Marcenaria, Serralheria, etc.
    items: List[KitItemInput] = []

class KitUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    sector: Optional[str] = None
    items: Optional[List[KitItemInput]] = None

class KitResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    sector: Optional[str] = None
    items: List[dict] = []
    created_at: datetime

# ===================== DELIVERY =====================

class DeliveryItemInput(BaseModel):
    epi_id: Optional[str] = None
    kit_id: Optional[str] = None
    quantity: int = 1
    size: Optional[str] = None
    batch: Optional[str] = None
    qr_code: Optional[str] = None
    condition: ItemCondition = ItemCondition.NEW
    notes: Optional[str] = None

class DeliveryCreate(BaseModel):
    employee_id: str
    delivery_type: str
    is_return: bool = False
    facial_match_score: Optional[float] = None
    facial_photo_path: Optional[str] = None  # Foto de comprovante da entrega
    notes: Optional[str] = None
    items: List[DeliveryItemInput]

class DeliveryResponse(BaseModel):
    id: str
    employee_id: str
    employee_name: Optional[str] = None
    delivery_type: str
    is_return: bool
    photo_evidence_path: Optional[str] = None
    facial_match_score: Optional[float] = None
    facial_photo_path: Optional[str] = None
    notes: Optional[str] = None
    items: List[dict] = []
    delivered_by: Optional[str] = None
    created_at: datetime

# ===================== STOCK =====================

class StockMovementResponse(BaseModel):
    id: str
    movement_type: StockMovementType
    epi_id: Optional[str] = None
    quantity: int
    notes: Optional[str] = None
    created_at: datetime

# ===================== LICENSE =====================

class LicenseAddDaysRequest(BaseModel):
    days: int
    reason: Optional[str] = None

class LicenseResponse(BaseModel):
    id: str
    expires_at: datetime
    is_blocked: bool
    days_remaining: int

# ===================== FACIAL TEMPLATE =====================

class FacialTemplateCreate(BaseModel):
    descriptor: str

class FacialTemplateResponse(BaseModel):
    id: str
    employee_id: str
    descriptor: str
    created_at: datetime
