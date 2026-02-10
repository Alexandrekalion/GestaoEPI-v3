from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from database import connect_db, close_db, get_db
from schemas import *
from auth import *
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from pathlib import Path
from bson import ObjectId
import os
import shutil
import logging
import base64
import io

# Para importação de Excel
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

# Para geração de PDF
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).parent
UPLOAD_DIR = ROOT_DIR / 'uploads'
UPLOAD_DIR.mkdir(exist_ok=True)

# Dias para expiração de senha
PASSWORD_EXPIRY_DAYS = 30

app = FastAPI(title='Cipolatti API')
api_router = APIRouter(prefix='/api')

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)

app.mount('/uploads', StaticFiles(directory=str(UPLOAD_DIR)), name='uploads')

@app.on_event('startup')
async def startup_event():
    await connect_db()
    from seed import seed_database
    await seed_database()

@app.on_event('shutdown')
async def shutdown_event():
    await close_db()

def doc_to_response(doc, id_field='id'):
    if doc is None:
        return None
    result = {k: v for k, v in doc.items() if k != '_id'}
    result[id_field] = str(doc['_id'])
    return result

def check_password_expired(user):
    """Verifica se a senha expirou (mais de 30 dias)"""
    password_changed_at = user.get('password_changed_at')
    if not password_changed_at:
        return False
    
    if password_changed_at.tzinfo is None:
        password_changed_at = password_changed_at.replace(tzinfo=timezone.utc)
    
    expiry_date = password_changed_at + timedelta(days=PASSWORD_EXPIRY_DAYS)
    return datetime.now(timezone.utc) > expiry_date

# Permissões por perfil
ROLE_PERMISSIONS = {
    'admin': ['all'],
    'gestor': ['dashboard', 'entrega', 'colaboradores', 'empresas', 'epis', 'fornecedores', 'kits'],
    'rh': ['dashboard', 'colaboradores', 'colaboradores_full', 'empresas', 'usuarios'],
    'seguranca_trabalho': ['dashboard', 'epis', 'fornecedores', 'kits', 'colaboradores_list'],
    'almoxarifado': ['dashboard', 'entrega', 'colaboradores_list']
}

def can_view_sensitive_data(role):
    """Verifica se o perfil pode ver dados sensíveis (CPF, RG, etc)"""
    return role in ['admin', 'gestor', 'rh']

def can_manage_users(role):
    """Verifica se pode gerenciar usuários"""
    return role in ['admin', 'rh']

def can_deliver_epi(role):
    """Verifica se pode fazer entregas de EPI"""
    return role in ['admin', 'gestor', 'almoxarifado']

def can_manage_epis(role):
    """Verifica se pode gerenciar EPIs"""
    return role in ['admin', 'gestor', 'seguranca_trabalho']

def can_manage_employees(role):
    """Verifica se pode cadastrar/editar colaboradores"""
    return role in ['admin', 'gestor', 'rh']

# ===================== AUTH =====================

@api_router.get('/')
async def root():
    return {'message': 'Cipolatti API'}

@api_router.post('/auth/login', response_model=TokenResponse)
async def login(request: LoginRequest):
    db = await get_db()
    user = await db.users.find_one({"username": request.username})
    
    if not user or not verify_password(request.password, user['hashed_password']):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Credenciais inválidas')
    
    if not user.get('is_active', True):
        raise HTTPException(status_code=400, detail='Usuário inativo')
    
    license_doc = await db.panel_license.find_one({})
    if license_doc:
        now = datetime.now(timezone.utc)
        expires_at = license_doc['expires_at']
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if now > expires_at and user['role'] != 'admin':
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Licença expirada')
    
    password_expired = check_password_expired(user)
    
    access_token = create_access_token(data={'sub': user['username'], 'role': user['role']})
    
    return TokenResponse(
        access_token=access_token,
        token_type='bearer',
        must_change_password=user.get('must_change_password', False),
        password_expired=password_expired,
        role=UserRole(user['role'])
    )

@api_router.post('/auth/change-password')
async def change_password(request: ChangePasswordRequest, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    if not verify_password(request.old_password, current_user['hashed_password']):
        raise HTTPException(status_code=400, detail='Senha antiga incorreta')
    
    await db.users.update_one(
        {"_id": ObjectId(current_user['id'])},
        {"$set": {
            "hashed_password": get_password_hash(request.new_password), 
            "must_change_password": False,
            "password_changed_at": datetime.now(timezone.utc)
        }}
    )
    return {'message': 'Senha alterada com sucesso'}

@api_router.get('/auth/me', response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    return UserResponse(
        id=current_user['id'],
        username=current_user['username'],
        email=current_user['email'],
        role=UserRole(current_user['role']),
        is_active=current_user.get('is_active', True),
        must_change_password=current_user.get('must_change_password', False),
        password_changed_at=current_user.get('password_changed_at'),
        employee_id=current_user.get('employee_id'),
        created_at=current_user.get('created_at', datetime.now(timezone.utc))
    )

# ===================== USERS =====================

@api_router.get('/users', response_model=List[UserResponse])
async def get_users(current_user: dict = Depends(require_role('admin', 'rh'))):
    db = await get_db()
    users = await db.users.find({}).to_list(1000)
    return [UserResponse(**doc_to_response(u)) for u in users]

@api_router.post('/users', response_model=UserResponse)
async def create_user(user_data: UserCreate, current_user: dict = Depends(require_role('admin', 'rh'))):
    db = await get_db()
    
    # RH não pode criar admins
    if current_user['role'] == 'rh' and user_data.role == UserRole.ADMIN:
        raise HTTPException(status_code=403, detail='Sem permissão para criar administradores')
    
    existing = await db.users.find_one({"$or": [{"username": user_data.username}, {"email": user_data.email}]})
    if existing:
        raise HTTPException(status_code=400, detail='Usuário ou email já existe')
    
    new_user = {
        "username": user_data.username,
        "email": user_data.email,
        "hashed_password": get_password_hash(user_data.password),
        "role": user_data.role.value,
        "employee_id": user_data.employee_id,
        "must_change_password": True,
        "is_active": True,
        "password_changed_at": datetime.now(timezone.utc),
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    }
    result = await db.users.insert_one(new_user)
    new_user['_id'] = result.inserted_id
    return UserResponse(**doc_to_response(new_user))

@api_router.patch('/users/{user_id}', response_model=UserResponse)
async def update_user(user_id: str, user_data: UserUpdate, current_user: dict = Depends(require_role('admin'))):
    db = await get_db()
    update_data = {k: v for k, v in user_data.model_dump(exclude_unset=True).items()}
    if 'role' in update_data:
        update_data['role'] = update_data['role'].value
    update_data['updated_at'] = datetime.now(timezone.utc)
    
    result = await db.users.find_one_and_update(
        {"_id": ObjectId(user_id)}, {"$set": update_data}, return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail='Usuário não encontrado')
    return UserResponse(**doc_to_response(result))

@api_router.delete('/users/{user_id}')
async def delete_user(user_id: str, current_user: dict = Depends(require_role('admin'))):
    db = await get_db()
    result = await db.users.delete_one({"_id": ObjectId(user_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail='Usuário não encontrado')
    return {'message': 'Usuário excluído'}

class ResetPasswordRequest(BaseModel):
    new_password: str

@api_router.post('/users/{user_id}/reset-password')
async def reset_user_password(user_id: str, request: ResetPasswordRequest, current_user: dict = Depends(require_role('admin'))):
    """Permite ao administrador redefinir a senha de qualquer usuário"""
    db = await get_db()
    
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail='Usuário não encontrado')
    
    # Validar complexidade da senha
    password = request.new_password
    import re
    if len(password) < 8:
        raise HTTPException(status_code=400, detail='A senha deve ter no mínimo 8 caracteres')
    if not re.search(r'[A-Z]', password):
        raise HTTPException(status_code=400, detail='A senha deve conter pelo menos uma letra maiúscula')
    if not re.search(r'[a-z]', password):
        raise HTTPException(status_code=400, detail='A senha deve conter pelo menos uma letra minúscula')
    if not re.search(r'\d', password):
        raise HTTPException(status_code=400, detail='A senha deve conter pelo menos um número')
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        raise HTTPException(status_code=400, detail='A senha deve conter pelo menos um caractere especial')
    
    await db.users.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {
            "hashed_password": get_password_hash(password),
            "must_change_password": True,
            "password_changed_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }}
    )
    
    return {'message': 'Senha redefinida com sucesso'}

# ===================== COMPANIES =====================

@api_router.get('/companies', response_model=List[CompanyResponse])
async def get_companies(current_user: dict = Depends(require_role('admin', 'gestor', 'rh'))):
    db = await get_db()
    companies = await db.companies.find({}).to_list(1000)
    return [CompanyResponse(**doc_to_response(c)) for c in companies]

@api_router.post('/companies', response_model=CompanyResponse)
async def create_company(company_data: CompanyCreate, current_user: dict = Depends(require_role('admin', 'gestor', 'rh'))):
    db = await get_db()
    existing = await db.companies.find_one({"cnpj": company_data.cnpj})
    if existing:
        raise HTTPException(status_code=400, detail='CNPJ já cadastrado')
    
    new_company = {**company_data.model_dump(), "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)}
    result = await db.companies.insert_one(new_company)
    new_company['_id'] = result.inserted_id
    return CompanyResponse(**doc_to_response(new_company))

@api_router.get('/companies/{company_id}', response_model=CompanyResponse)
async def get_company(company_id: str, current_user: dict = Depends(require_role('admin', 'gestor', 'rh'))):
    db = await get_db()
    company = await db.companies.find_one({"_id": ObjectId(company_id)})
    if not company:
        raise HTTPException(status_code=404, detail='Empresa não encontrada')
    return CompanyResponse(**doc_to_response(company))

@api_router.patch('/companies/{company_id}', response_model=CompanyResponse)
async def update_company(company_id: str, company_data: CompanyUpdate, current_user: dict = Depends(require_role('admin', 'gestor', 'rh'))):
    db = await get_db()
    update_data = {k: v for k, v in company_data.model_dump(exclude_unset=True).items()}
    update_data['updated_at'] = datetime.now(timezone.utc)
    result = await db.companies.find_one_and_update(
        {"_id": ObjectId(company_id)}, {"$set": update_data}, return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail='Empresa não encontrada')
    return CompanyResponse(**doc_to_response(result))

@api_router.delete('/companies/{company_id}')
async def delete_company(company_id: str, current_user: dict = Depends(require_role('admin'))):
    db = await get_db()
    result = await db.companies.delete_one({"_id": ObjectId(company_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail='Empresa não encontrada')
    return {'message': 'Empresa excluída'}

# ===================== EMPLOYEES =====================

@api_router.get('/employees')
async def get_employees(current_user: dict = Depends(get_current_user), search: Optional[str] = None, company_id: Optional[str] = None):
    db = await get_db()
    query = {}
    if search:
        query["$or"] = [
            {"full_name": {"$regex": search, "$options": "i"}},
            {"cpf": {"$regex": search, "$options": "i"}},
            {"registration_number": {"$regex": search, "$options": "i"}}
        ]
    if company_id:
        query["company_id"] = company_id
    
    employees = await db.employees.find(query).to_list(1000)
    
    # Perfis que não podem ver dados sensíveis
    if not can_view_sensitive_data(current_user['role']):
        return [EmployeePublicResponse(**doc_to_response(e)) for e in employees]
    
    return [EmployeeResponse(**doc_to_response(e)) for e in employees]

@api_router.post('/employees', response_model=EmployeeResponse)
async def create_employee(employee_data: EmployeeCreate, current_user: dict = Depends(get_current_user)):
    if not can_manage_employees(current_user['role']):
        raise HTTPException(status_code=403, detail='Sem permissão para cadastrar colaboradores')
    
    db = await get_db()
    existing = await db.employees.find_one({"cpf": employee_data.cpf})
    if existing:
        raise HTTPException(status_code=400, detail='CPF já cadastrado')
    
    new_employee = {**employee_data.model_dump(), "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)}
    result = await db.employees.insert_one(new_employee)
    new_employee['_id'] = result.inserted_id
    return EmployeeResponse(**doc_to_response(new_employee))

@api_router.get('/employees/{employee_id}')
async def get_employee(employee_id: str, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    employee = await db.employees.find_one({"_id": ObjectId(employee_id)})
    if not employee:
        raise HTTPException(status_code=404, detail='Colaborador não encontrado')
    
    if not can_view_sensitive_data(current_user['role']):
        return EmployeePublicResponse(**doc_to_response(employee))
    
    return EmployeeResponse(**doc_to_response(employee))

@api_router.patch('/employees/{employee_id}', response_model=EmployeeResponse)
async def update_employee(employee_id: str, employee_data: EmployeeUpdate, current_user: dict = Depends(get_current_user)):
    if not can_manage_employees(current_user['role']):
        raise HTTPException(status_code=403, detail='Sem permissão para editar colaboradores')
    
    db = await get_db()
    update_data = {k: v for k, v in employee_data.model_dump(exclude_unset=True).items()}
    update_data['updated_at'] = datetime.now(timezone.utc)
    result = await db.employees.find_one_and_update(
        {"_id": ObjectId(employee_id)}, {"$set": update_data}, return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail='Colaborador não encontrado')
    return EmployeeResponse(**doc_to_response(result))

@api_router.delete('/employees/{employee_id}')
async def delete_employee(employee_id: str, current_user: dict = Depends(require_role('admin'))):
    db = await get_db()
    result = await db.employees.delete_one({"_id": ObjectId(employee_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail='Colaborador não encontrado')
    return {'message': 'Colaborador excluído'}

@api_router.post('/employees/{employee_id}/photo')
async def upload_employee_photo(employee_id: str, file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    if not can_manage_employees(current_user['role']):
        raise HTTPException(status_code=403, detail='Sem permissão')
    
    db = await get_db()
    employee = await db.employees.find_one({"_id": ObjectId(employee_id)})
    if not employee:
        raise HTTPException(status_code=404, detail='Colaborador não encontrado')
    
    file_ext = Path(file.filename).suffix
    file_name = f'employee_{employee_id}_{datetime.now(timezone.utc).timestamp()}{file_ext}'
    file_path = UPLOAD_DIR / 'employees' / file_name
    file_path.parent.mkdir(exist_ok=True, parents=True)
    
    with file_path.open('wb') as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    photo_path = f'/uploads/employees/{file_name}'
    await db.employees.update_one({"_id": ObjectId(employee_id)}, {"$set": {"photo_path": photo_path}})
    return {'photo_path': photo_path}

# ===================== IMPORTAÇÃO/EXPORTAÇÃO =====================

@api_router.get('/employees/export/excel')
async def export_employees_excel(current_user: dict = Depends(get_current_user)):
    """Exporta colaboradores para Excel"""
    if not can_manage_employees(current_user['role']):
        raise HTTPException(status_code=403, detail='Permissão insuficiente')
    
    db = await get_db()
    employees = await db.employees.find().to_list(5000)
    companies = {str(c['_id']): c['legal_name'] async for c in db.companies.find()}
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Colaboradores"
    
    # Cabeçalho
    headers = ['Nome Completo', 'CPF', 'RG', 'Matrícula', 'Empresa', 'Cargo', 'Setor', 'Status']
    header_fill = PatternFill(start_color="10B981", end_color="10B981", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')
    
    # Dados
    for row, emp in enumerate(employees, 2):
        ws.cell(row=row, column=1, value=emp.get('full_name', ''))
        ws.cell(row=row, column=2, value=emp.get('cpf', ''))
        ws.cell(row=row, column=3, value=emp.get('rg', ''))
        ws.cell(row=row, column=4, value=emp.get('registration_number', ''))
        ws.cell(row=row, column=5, value=companies.get(emp.get('company_id', ''), ''))
        ws.cell(row=row, column=6, value=emp.get('position', ''))
        ws.cell(row=row, column=7, value=emp.get('department', ''))
        ws.cell(row=row, column=8, value='Ativo' if emp.get('status') == 'active' else 'Inativo')
    
    # Ajustar largura das colunas
    for col in ws.columns:
        max_length = max(len(str(cell.value or '')) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = max_length + 2
    
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    return StreamingResponse(
        output,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename=colaboradores_{datetime.now().strftime("%Y%m%d")}.xlsx'}
    )

@api_router.get('/employees/template/excel')
async def download_employees_template(current_user: dict = Depends(get_current_user)):
    """Download do template Excel para importação de colaboradores"""
    wb = Workbook()
    ws = wb.active
    ws.title = "Colaboradores"
    
    # Cabeçalho com instruções
    headers = ['Nome Completo*', 'CPF*', 'RG', 'Matrícula*', 'Empresa*', 'Cargo', 'Setor', 'Status']
    header_fill = PatternFill(start_color="10B981", end_color="10B981", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')
    
    # Exemplo de preenchimento
    ws.cell(row=2, column=1, value='João da Silva')
    ws.cell(row=2, column=2, value='123.456.789-00')
    ws.cell(row=2, column=3, value='12.345.678-9')
    ws.cell(row=2, column=4, value='MAT001')
    ws.cell(row=2, column=5, value='Nome da Empresa')
    ws.cell(row=2, column=6, value='Operador')
    ws.cell(row=2, column=7, value='Produção')
    ws.cell(row=2, column=8, value='Ativo')
    
    # Instruções
    ws2 = wb.create_sheet(title="Instruções")
    ws2.cell(row=1, column=1, value="INSTRUÇÕES DE PREENCHIMENTO").font = Font(bold=True, size=14)
    ws2.cell(row=3, column=1, value="* Campos obrigatórios")
    ws2.cell(row=4, column=1, value="• Nome Completo: Nome completo do colaborador")
    ws2.cell(row=5, column=1, value="• CPF: Formato XXX.XXX.XXX-XX ou apenas números")
    ws2.cell(row=6, column=1, value="• Matrícula: Código único do colaborador na empresa")
    ws2.cell(row=7, column=1, value="• Empresa: Nome exato da empresa cadastrada no sistema")
    ws2.cell(row=8, column=1, value="• Status: 'Ativo' ou 'Inativo' (padrão: Ativo)")
    
    for col in ws.columns:
        max_length = max(len(str(cell.value or '')) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = max_length + 2
    
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    return StreamingResponse(
        output,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': 'attachment; filename=template_colaboradores.xlsx'}
    )

@api_router.post('/employees/import/excel')
async def import_employees_excel(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """Importa colaboradores de um arquivo Excel"""
    if not can_manage_employees(current_user['role']):
        raise HTTPException(status_code=403, detail='Permissão insuficiente')
    
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail='Arquivo deve ser Excel (.xlsx ou .xls)')
    
    db = await get_db()
    
    # Carregar empresas
    companies = {}
    async for company in db.companies.find():
        companies[company['legal_name'].lower().strip()] = str(company['_id'])
    
    try:
        content = await file.read()
        wb = load_workbook(io.BytesIO(content))
        ws = wb.active
        
        results = {'imported': 0, 'errors': [], 'skipped': 0}
        
        for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
            if not row or not row[0]:  # Linha vazia
                continue
            
            full_name = str(row[0]).strip() if row[0] else None
            cpf = str(row[1]).strip() if row[1] else None
            rg = str(row[2]).strip() if row[2] else None
            registration_number = str(row[3]).strip() if row[3] else None
            company_name = str(row[4]).strip().lower() if row[4] else None
            position = str(row[5]).strip() if len(row) > 5 and row[5] else None
            department = str(row[6]).strip() if len(row) > 6 and row[6] else None
            status_str = str(row[7]).strip().lower() if len(row) > 7 and row[7] else 'ativo'
            
            # Validações
            errors = []
            if not full_name:
                errors.append('Nome é obrigatório')
            if not cpf:
                errors.append('CPF é obrigatório')
            if not registration_number:
                errors.append('Matrícula é obrigatória')
            if not company_name:
                errors.append('Empresa é obrigatória')
            elif company_name not in companies:
                errors.append(f'Empresa "{row[4]}" não encontrada no sistema')
            
            if errors:
                results['errors'].append({'row': row_num, 'errors': errors, 'name': full_name})
                continue
            
            # Verificar se já existe
            existing = await db.employees.find_one({
                "$or": [
                    {"cpf": cpf},
                    {"registration_number": registration_number, "company_id": companies.get(company_name)}
                ]
            })
            
            if existing:
                results['skipped'] += 1
                results['errors'].append({
                    'row': row_num, 
                    'errors': ['Colaborador já existe (CPF ou Matrícula duplicada)'],
                    'name': full_name
                })
                continue
            
            # Inserir colaborador
            employee = {
                'full_name': full_name,
                'cpf': cpf,
                'rg': rg,
                'registration_number': registration_number,
                'company_id': companies.get(company_name),
                'position': position,
                'department': department,
                'status': 'active' if status_str == 'ativo' else 'inactive',
                'facial_consent': False,
                'created_at': datetime.now(timezone.utc),
                'updated_at': datetime.now(timezone.utc)
            }
            
            await db.employees.insert_one(employee)
            results['imported'] += 1
        
        return results
        
    except Exception as e:
        logger.error(f"Erro ao importar Excel: {str(e)}")
        raise HTTPException(status_code=400, detail=f'Erro ao processar arquivo: {str(e)}')

# ===================== IMPRESSÃO PDF =====================

@api_router.get('/reports/employees/pdf')
async def generate_employees_pdf(current_user: dict = Depends(get_current_user)):
    """Gera relatório PDF de colaboradores"""
    if not can_view_sensitive_data(current_user['role']):
        raise HTTPException(status_code=403, detail='Permissão insuficiente')
    
    db = await get_db()
    employees = await db.employees.find({"status": "active"}).to_list(5000)
    companies = {str(c['_id']): c['legal_name'] async for c in db.companies.find()}
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=20, leftMargin=20, topMargin=30, bottomMargin=30)
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=16, alignment=1, spaceAfter=20)
    
    elements = []
    
    # Título
    elements.append(Paragraph("Relatório de Colaboradores", title_style))
    elements.append(Paragraph(f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles['Normal']))
    elements.append(Spacer(1, 20))
    
    # Tabela
    data = [['Nome', 'CPF', 'Matrícula', 'Empresa', 'Cargo', 'Setor']]
    
    for emp in employees:
        data.append([
            emp.get('full_name', '')[:30],
            emp.get('cpf', ''),
            emp.get('registration_number', ''),
            companies.get(emp.get('company_id', ''), '')[:25],
            (emp.get('position', '') or '')[:20],
            (emp.get('department', '') or '')[:15]
        ])
    
    table = Table(data, colWidths=[120, 90, 70, 120, 100, 80])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.063, 0.725, 0.506)),  # Emerald
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.Color(0.95, 0.95, 0.95)]),
    ]))
    
    elements.append(table)
    elements.append(Spacer(1, 20))
    elements.append(Paragraph(f"Total de colaboradores ativos: {len(employees)}", styles['Normal']))
    
    doc.build(elements)
    buffer.seek(0)
    
    return StreamingResponse(
        buffer,
        media_type='application/pdf',
        headers={'Content-Disposition': f'attachment; filename=colaboradores_{datetime.now().strftime("%Y%m%d")}.pdf'}
    )

@api_router.get('/reports/deliveries/pdf')
async def generate_deliveries_pdf(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Gera relatório PDF de entregas"""
    db = await get_db()
    
    query = {}
    if start_date:
        query['created_at'] = {'$gte': datetime.fromisoformat(start_date.replace('Z', '+00:00'))}
    if end_date:
        if 'created_at' not in query:
            query['created_at'] = {}
        query['created_at']['$lte'] = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
    
    deliveries = await db.deliveries.find(query).sort('created_at', -1).to_list(1000)
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=20, leftMargin=20, topMargin=30, bottomMargin=30)
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=16, alignment=1, spaceAfter=20)
    
    elements = []
    
    # Título
    elements.append(Paragraph("Relatório de Entregas de EPIs", title_style))
    elements.append(Paragraph(f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles['Normal']))
    elements.append(Spacer(1, 20))
    
    # Tabela
    data = [['Data', 'Colaborador', 'Itens', 'Tipo', 'Verificação Facial']]
    
    for delivery in deliveries:
        items_str = ', '.join([
            f"{item.get('quantity', 1)}x {item.get('epi_name', item.get('kit_name', 'Item'))}"
            for item in delivery.get('items', [])
        ])[:50]
        
        facial_match = delivery.get('facial_match_score')
        facial_str = f"{int(facial_match * 100)}%" if facial_match else 'N/A'
        
        data.append([
            delivery.get('created_at', datetime.now()).strftime('%d/%m/%Y %H:%M'),
            delivery.get('employee_name', '')[:25],
            items_str,
            'Devolução' if delivery.get('is_return') else 'Entrega',
            facial_str
        ])
    
    table = Table(data, colWidths=[100, 150, 200, 70, 80])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.063, 0.725, 0.506)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.Color(0.95, 0.95, 0.95)]),
    ]))
    
    elements.append(table)
    elements.append(Spacer(1, 20))
    elements.append(Paragraph(f"Total de entregas: {len(deliveries)}", styles['Normal']))
    
    doc.build(elements)
    buffer.seek(0)
    
    return StreamingResponse(
        buffer,
        media_type='application/pdf',
        headers={'Content-Disposition': f'attachment; filename=entregas_{datetime.now().strftime("%Y%m%d")}.pdf'}
    )

@api_router.get('/reports/employee/{employee_id}/pdf')
async def generate_employee_history_pdf(employee_id: str, current_user: dict = Depends(get_current_user)):
    """Gera PDF com ficha do colaborador e histórico de entregas"""
    db = await get_db()
    
    employee = await db.employees.find_one({"_id": ObjectId(employee_id)})
    if not employee:
        raise HTTPException(status_code=404, detail='Colaborador não encontrado')
    
    company = None
    if employee.get('company_id'):
        company = await db.companies.find_one({"_id": ObjectId(employee['company_id'])})
    
    deliveries = await db.deliveries.find({"employee_id": employee_id}).sort('created_at', -1).to_list(500)
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=40, bottomMargin=40)
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=18, alignment=1, spaceAfter=20)
    subtitle_style = ParagraphStyle('Subtitle', parent=styles['Heading2'], fontSize=14, spaceAfter=10)
    
    elements = []
    
    # Cabeçalho
    elements.append(Paragraph("Ficha do Colaborador", title_style))
    elements.append(Spacer(1, 10))
    
    # Dados do colaborador
    info_data = [
        ['Nome:', employee.get('full_name', '')],
        ['CPF:', employee.get('cpf', '')],
        ['RG:', employee.get('rg', '') or '-'],
        ['Matrícula:', employee.get('registration_number', '')],
        ['Empresa:', company.get('legal_name', '') if company else '-'],
        ['Cargo:', employee.get('position', '') or '-'],
        ['Setor:', employee.get('department', '') or '-'],
        ['Status:', 'Ativo' if employee.get('status') == 'active' else 'Inativo'],
    ]
    
    info_table = Table(info_data, colWidths=[100, 350])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
    ]))
    
    elements.append(info_table)
    elements.append(Spacer(1, 30))
    
    # Histórico de entregas
    elements.append(Paragraph("Histórico de Entregas/Devoluções", subtitle_style))
    
    if deliveries:
        history_data = [['Data', 'Tipo', 'Itens', 'Verificação']]
        
        for delivery in deliveries:
            items_str = ', '.join([
                f"{item.get('quantity', 1)}x {item.get('epi_name', item.get('kit_name', 'Item'))}"
                for item in delivery.get('items', [])
            ])[:60]
            
            facial_match = delivery.get('facial_match_score')
            facial_str = f"{int(facial_match * 100)}%" if facial_match else '-'
            
            history_data.append([
                delivery.get('created_at', datetime.now()).strftime('%d/%m/%Y'),
                'Devolução' if delivery.get('is_return') else 'Entrega',
                items_str,
                facial_str
            ])
        
        history_table = Table(history_data, colWidths=[80, 70, 250, 60])
        history_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.063, 0.725, 0.506)),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.Color(0.95, 0.95, 0.95)]),
        ]))
        
        elements.append(history_table)
    else:
        elements.append(Paragraph("Nenhuma entrega registrada.", styles['Normal']))
    
    elements.append(Spacer(1, 40))
    elements.append(Paragraph(f"Documento gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles['Normal']))
    
    doc.build(elements)
    buffer.seek(0)
    
    return StreamingResponse(
        buffer,
        media_type='application/pdf',
        headers={'Content-Disposition': f'attachment; filename=ficha_{employee.get("registration_number", employee_id)}_{datetime.now().strftime("%Y%m%d")}.pdf'}
    )

# ===================== FACIAL TEMPLATES =====================

@api_router.get('/employees/{employee_id}/facial-templates')
async def get_facial_templates(employee_id: str, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    templates = await db.facial_templates.find({"employee_id": employee_id}).to_list(100)
    return [doc_to_response(t) for t in templates]

@api_router.post('/employees/{employee_id}/facial-templates')
async def create_facial_template(employee_id: str, template_data: FacialTemplateCreate, current_user: dict = Depends(get_current_user)):
    if not can_manage_employees(current_user['role']):
        raise HTTPException(status_code=403, detail='Sem permissão')
    
    db = await get_db()
    employee = await db.employees.find_one({"_id": ObjectId(employee_id)})
    if not employee:
        raise HTTPException(status_code=404, detail='Colaborador não encontrado')
    
    new_template = {
        "employee_id": employee_id,
        "descriptor": template_data.descriptor,
        "created_at": datetime.now(timezone.utc)
    }
    result = await db.facial_templates.insert_one(new_template)
    new_template['_id'] = result.inserted_id
    return doc_to_response(new_template)

@api_router.delete('/employees/{employee_id}/facial-templates/{template_id}')
async def delete_facial_template(employee_id: str, template_id: str, current_user: dict = Depends(get_current_user)):
    if not can_manage_employees(current_user['role']):
        raise HTTPException(status_code=403, detail='Sem permissão')
    
    db = await get_db()
    result = await db.facial_templates.delete_one({
        "_id": ObjectId(template_id),
        "employee_id": employee_id
    })
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail='Template não encontrado')
    
    return {'message': 'Template excluído'}

# ===================== SUPPLIERS =====================

@api_router.get('/suppliers', response_model=List[SupplierResponse])
async def get_suppliers(current_user: dict = Depends(require_role('admin', 'gestor', 'seguranca_trabalho'))):
    db = await get_db()
    suppliers = await db.suppliers.find({}).to_list(1000)
    return [SupplierResponse(**doc_to_response(s)) for s in suppliers]

@api_router.post('/suppliers', response_model=SupplierResponse)
async def create_supplier(supplier_data: SupplierCreate, current_user: dict = Depends(require_role('admin', 'gestor', 'seguranca_trabalho'))):
    db = await get_db()
    new_supplier = {**supplier_data.model_dump(), "created_at": datetime.now(timezone.utc)}
    result = await db.suppliers.insert_one(new_supplier)
    new_supplier['_id'] = result.inserted_id
    return SupplierResponse(**doc_to_response(new_supplier))

@api_router.patch('/suppliers/{supplier_id}', response_model=SupplierResponse)
async def update_supplier(supplier_id: str, supplier_data: SupplierUpdate, current_user: dict = Depends(require_role('admin', 'gestor', 'seguranca_trabalho'))):
    db = await get_db()
    update_data = {k: v for k, v in supplier_data.model_dump(exclude_unset=True).items()}
    update_data['updated_at'] = datetime.now(timezone.utc)
    result = await db.suppliers.find_one_and_update(
        {"_id": ObjectId(supplier_id)}, {"$set": update_data}, return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail='Fornecedor não encontrado')
    return SupplierResponse(**doc_to_response(result))

@api_router.delete('/suppliers/{supplier_id}')
async def delete_supplier(supplier_id: str, current_user: dict = Depends(require_role('admin'))):
    db = await get_db()
    result = await db.suppliers.delete_one({"_id": ObjectId(supplier_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail='Fornecedor não encontrado')
    return {'message': 'Fornecedor excluído'}

# ===================== EPIS =====================

def calculate_epi_status(epi):
    """Calcula status de estoque e validade do EPI"""
    stock_status = 'ok'
    validity_status = 'ok'
    
    # Status de estoque
    if epi.get('current_stock', 0) <= 0:
        stock_status = 'out'
    elif epi.get('current_stock', 0) <= epi.get('min_stock', 0):
        stock_status = 'low'
    
    # Status de validade
    validity_date = epi.get('validity_date') or epi.get('ca_validity')
    if validity_date:
        if validity_date.tzinfo is None:
            validity_date = validity_date.replace(tzinfo=timezone.utc)
        
        now = datetime.now(timezone.utc)
        days_until_expiry = (validity_date - now).days
        
        if days_until_expiry < 0:
            validity_status = 'expired'
        elif days_until_expiry <= 30:
            validity_status = 'expiring'
    
    return stock_status, validity_status

@api_router.get('/epis', response_model=List[EPIResponse])
async def get_epis(current_user: dict = Depends(require_role('admin', 'gestor', 'seguranca_trabalho', 'almoxarifado'))):
    db = await get_db()
    epis = await db.epis.find({}).to_list(1000)
    
    result = []
    for e in epis:
        stock_status, validity_status = calculate_epi_status(e)
        resp = doc_to_response(e)
        resp['stock_status'] = stock_status
        resp['validity_status'] = validity_status
        result.append(EPIResponse(**resp))
    
    return result

@api_router.post('/epis', response_model=EPIResponse)
async def create_epi(epi_data: EPICreate, current_user: dict = Depends(require_role('admin', 'gestor', 'seguranca_trabalho'))):
    db = await get_db()
    new_epi = {**epi_data.model_dump(), "created_by": current_user['id'], "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)}
    result = await db.epis.insert_one(new_epi)
    new_epi['_id'] = result.inserted_id
    stock_status, validity_status = calculate_epi_status(new_epi)
    resp = doc_to_response(new_epi)
    resp['stock_status'] = stock_status
    resp['validity_status'] = validity_status
    return EPIResponse(**resp)

@api_router.get('/epis/{epi_id}', response_model=EPIResponse)
async def get_epi(epi_id: str, current_user: dict = Depends(require_role('admin', 'gestor', 'seguranca_trabalho', 'almoxarifado'))):
    db = await get_db()
    epi = await db.epis.find_one({"_id": ObjectId(epi_id)})
    if not epi:
        raise HTTPException(status_code=404, detail='EPI não encontrado')
    stock_status, validity_status = calculate_epi_status(epi)
    resp = doc_to_response(epi)
    resp['stock_status'] = stock_status
    resp['validity_status'] = validity_status
    return EPIResponse(**resp)

@api_router.patch('/epis/{epi_id}', response_model=EPIResponse)
async def update_epi(epi_id: str, epi_data: EPIUpdate, current_user: dict = Depends(require_role('admin', 'gestor', 'seguranca_trabalho'))):
    db = await get_db()
    update_data = {k: v for k, v in epi_data.model_dump(exclude_unset=True).items()}
    update_data['updated_at'] = datetime.now(timezone.utc)
    result = await db.epis.find_one_and_update({"_id": ObjectId(epi_id)}, {"$set": update_data}, return_document=True)
    if not result:
        raise HTTPException(status_code=404, detail='EPI não encontrado')
    stock_status, validity_status = calculate_epi_status(result)
    resp = doc_to_response(result)
    resp['stock_status'] = stock_status
    resp['validity_status'] = validity_status
    return EPIResponse(**resp)

@api_router.delete('/epis/{epi_id}')
async def delete_epi(epi_id: str, current_user: dict = Depends(require_role('admin'))):
    db = await get_db()
    result = await db.epis.delete_one({"_id": ObjectId(epi_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail='EPI não encontrado')
    return {'message': 'EPI excluído'}

# ===================== KITS =====================

@api_router.get('/kits', response_model=List[KitResponse])
async def get_kits(current_user: dict = Depends(require_role('admin', 'gestor', 'seguranca_trabalho', 'almoxarifado'))):
    db = await get_db()
    kits = await db.kits.find({}).to_list(1000)
    return [KitResponse(**doc_to_response(k)) for k in kits]

@api_router.post('/kits', response_model=KitResponse)
async def create_kit(kit_data: KitCreate, current_user: dict = Depends(require_role('admin', 'gestor', 'seguranca_trabalho'))):
    db = await get_db()
    
    # Buscar detalhes dos EPIs para armazenar nome e descrição
    items_with_details = []
    for item in kit_data.items:
        if item.epi_id:
            epi = await db.epis.find_one({"_id": ObjectId(item.epi_id)})
            if epi:
                items_with_details.append({
                    "epi_id": item.epi_id,
                    "name": epi['name'],
                    "type_category": epi.get('type_category', ''),
                    "ca_number": epi.get('ca_number', ''),
                    "size": epi.get('size', ''),
                    "quantity": item.quantity
                })
    
    new_kit = {
        "name": kit_data.name,
        "description": kit_data.description,
        "sector": kit_data.sector,
        "items": items_with_details,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    }
    result = await db.kits.insert_one(new_kit)
    new_kit['_id'] = result.inserted_id
    return KitResponse(**doc_to_response(new_kit))

@api_router.get('/kits/{kit_id}', response_model=KitResponse)
async def get_kit(kit_id: str, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    kit = await db.kits.find_one({"_id": ObjectId(kit_id)})
    if not kit:
        raise HTTPException(status_code=404, detail='Kit não encontrado')
    return KitResponse(**doc_to_response(kit))

@api_router.patch('/kits/{kit_id}', response_model=KitResponse)
async def update_kit(kit_id: str, kit_data: KitUpdate, current_user: dict = Depends(require_role('admin', 'gestor', 'seguranca_trabalho'))):
    db = await get_db()
    update_data = {}
    
    if kit_data.name is not None:
        update_data['name'] = kit_data.name
    if kit_data.description is not None:
        update_data['description'] = kit_data.description
    if kit_data.sector is not None:
        update_data['sector'] = kit_data.sector
    
    if kit_data.items is not None:
        items_with_details = []
        for item in kit_data.items:
            if item.epi_id:
                epi = await db.epis.find_one({"_id": ObjectId(item.epi_id)})
                if epi:
                    items_with_details.append({
                        "epi_id": item.epi_id,
                        "name": epi['name'],
                        "type_category": epi.get('type_category', ''),
                        "ca_number": epi.get('ca_number', ''),
                        "size": epi.get('size', ''),
                        "quantity": item.quantity
                    })
        update_data['items'] = items_with_details
    
    update_data['updated_at'] = datetime.now(timezone.utc)
    
    result = await db.kits.find_one_and_update(
        {"_id": ObjectId(kit_id)}, {"$set": update_data}, return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail='Kit não encontrado')
    return KitResponse(**doc_to_response(result))

@api_router.delete('/kits/{kit_id}')
async def delete_kit(kit_id: str, current_user: dict = Depends(require_role('admin'))):
    db = await get_db()
    result = await db.kits.delete_one({"_id": ObjectId(kit_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail='Kit não encontrado')
    return {'message': 'Kit excluído'}

# ===================== DELIVERIES =====================

@api_router.post('/deliveries', response_model=DeliveryResponse)
async def create_delivery(delivery_data: DeliveryCreate, current_user: dict = Depends(get_current_user)):
    if not can_deliver_epi(current_user['role']):
        raise HTTPException(status_code=403, detail='Sem permissão para realizar entregas')
    
    db = await get_db()
    
    employee = await db.employees.find_one({"_id": ObjectId(delivery_data.employee_id)})
    if not employee:
        raise HTTPException(status_code=404, detail='Colaborador não encontrado')
    
    # Verificar se colaborador tem foto cadastrada
    if not employee.get('photo_path'):
        raise HTTPException(status_code=400, detail='Colaborador não possui foto cadastrada. Procure o RH para cadastrar.')
    
    items_list = []
    for item in delivery_data.items:
        item_dict = item.model_dump()
        
        if item.epi_id:
            epi = await db.epis.find_one({"_id": ObjectId(item.epi_id)})
            if epi:
                item_dict['epi_name'] = epi['name']
                item_dict['ca_number'] = epi.get('ca_number', '')
                stock_change = -item.quantity if not delivery_data.is_return else item.quantity
                await db.epis.update_one({"_id": ObjectId(item.epi_id)}, {"$inc": {"current_stock": stock_change}})
                
                movement = {
                    "movement_type": "return" if delivery_data.is_return else "delivery",
                    "epi_id": item.epi_id,
                    "quantity": item.quantity if delivery_data.is_return else -item.quantity,
                    "employee_id": delivery_data.employee_id,
                    "created_by": current_user['id'],
                    "created_at": datetime.now(timezone.utc)
                }
                await db.stock_movements.insert_one(movement)
        
        if item.kit_id:
            kit = await db.kits.find_one({"_id": ObjectId(item.kit_id)})
            if kit:
                item_dict['kit_name'] = kit['name']
                # Processar itens do kit
                for kit_item in kit.get('items', []):
                    if kit_item.get('epi_id'):
                        stock_change = -kit_item['quantity'] if not delivery_data.is_return else kit_item['quantity']
                        await db.epis.update_one({"_id": ObjectId(kit_item['epi_id'])}, {"$inc": {"current_stock": stock_change}})
        
        items_list.append(item_dict)
    
    new_delivery = {
        "employee_id": delivery_data.employee_id,
        "employee_name": employee['full_name'],
        "delivery_type": delivery_data.delivery_type,
        "is_return": delivery_data.is_return,
        "facial_match_score": delivery_data.facial_match_score,
        "facial_photo_path": delivery_data.facial_photo_path,
        "notes": delivery_data.notes,
        "items": items_list,
        "delivered_by": current_user['id'],
        "delivered_by_name": current_user['username'],
        "created_at": datetime.now(timezone.utc)
    }
    result = await db.deliveries.insert_one(new_delivery)
    new_delivery['_id'] = result.inserted_id
    return DeliveryResponse(**doc_to_response(new_delivery))

@api_router.post('/deliveries/save-photo')
async def save_delivery_photo(
    employee_id: str = Form(...),
    photo_data: str = Form(...),
    current_user: dict = Depends(get_current_user)
):
    """Salva a foto de confirmação da entrega"""
    if not can_deliver_epi(current_user['role']):
        raise HTTPException(status_code=403, detail='Sem permissão')
    
    try:
        # Decodificar base64
        if ',' in photo_data:
            photo_data = photo_data.split(',')[1]
        
        photo_bytes = base64.b64decode(photo_data)
        
        file_name = f'delivery_{employee_id}_{datetime.now(timezone.utc).timestamp()}.jpg'
        file_path = UPLOAD_DIR / 'deliveries' / file_name
        file_path.parent.mkdir(exist_ok=True, parents=True)
        
        with open(file_path, 'wb') as f:
            f.write(photo_bytes)
        
        return {'photo_path': f'/uploads/deliveries/{file_name}'}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f'Erro ao salvar foto: {str(e)}')

@api_router.get('/deliveries', response_model=List[DeliveryResponse])
async def get_deliveries(
    current_user: dict = Depends(get_current_user), 
    employee_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    db = await get_db()
    query = {}
    if employee_id:
        query['employee_id'] = employee_id
    
    if start_date:
        query['created_at'] = query.get('created_at', {})
        query['created_at']['$gte'] = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
    
    if end_date:
        query['created_at'] = query.get('created_at', {})
        query['created_at']['$lte'] = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
    
    deliveries = await db.deliveries.find(query).sort("created_at", -1).to_list(1000)
    return [DeliveryResponse(**doc_to_response(d)) for d in deliveries]

# ===================== STOCK =====================

@api_router.get('/stock/alerts')
async def get_stock_alerts(current_user: dict = Depends(get_current_user)):
    db = await get_db()
    
    # EPIs com estoque baixo
    low_stock = await db.epis.find({"$expr": {"$lte": ["$current_stock", "$min_stock"]}}).to_list(100)
    
    # EPIs com validade próxima (30 dias)
    expiry_date = datetime.now(timezone.utc) + timedelta(days=30)
    expiring_soon = await db.epis.find({
        "$or": [
            {"validity_date": {"$ne": None, "$lte": expiry_date}},
            {"ca_validity": {"$ne": None, "$lte": expiry_date}}
        ]
    }).to_list(100)
    
    return {
        'low_stock': [{'id': str(e['_id']), 'name': e['name'], 'current_stock': e['current_stock'], 'min_stock': e['min_stock']} for e in low_stock],
        'expiring_soon': [{'id': str(e['_id']), 'name': e['name'], 'validity_date': e.get('validity_date') or e.get('ca_validity')} for e in expiring_soon]
    }

@api_router.get('/stock/movements')
async def get_stock_movements(current_user: dict = Depends(get_current_user), epi_id: Optional[str] = None):
    db = await get_db()
    query = {}
    if epi_id:
        query['epi_id'] = epi_id
    movements = await db.stock_movements.find(query).sort("created_at", -1).to_list(500)
    return [doc_to_response(m) for m in movements]

# ===================== LICENSE =====================

@api_router.get('/license', response_model=LicenseResponse)
async def get_license(current_user: dict = Depends(require_role('admin'))):
    db = await get_db()
    license_doc = await db.panel_license.find_one({})
    if not license_doc:
        raise HTTPException(status_code=404, detail='Licença não encontrada')
    
    now = datetime.now(timezone.utc)
    expires_at = license_doc['expires_at']
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    
    days_remaining = max(0, (expires_at - now).days)
    
    return LicenseResponse(
        id=str(license_doc['_id']),
        expires_at=license_doc['expires_at'],
        is_blocked=license_doc.get('is_blocked', False),
        days_remaining=days_remaining
    )

@api_router.post('/license/add-days')
async def add_license_days(request: LicenseAddDaysRequest, current_user: dict = Depends(require_role('admin'))):
    db = await get_db()
    license_doc = await db.panel_license.find_one({})
    if not license_doc:
        raise HTTPException(status_code=404, detail='Licença não encontrada')
    
    new_expires = license_doc['expires_at'] + timedelta(days=request.days)
    await db.panel_license.update_one({"_id": license_doc['_id']}, {"$set": {"expires_at": new_expires}})
    
    history = {
        "license_id": str(license_doc['_id']),
        "user_id": current_user['id'],
        "days_added": request.days,
        "reason": request.reason,
        "created_at": datetime.now(timezone.utc)
    }
    await db.license_history.insert_one(history)
    
    return {'message': f'{request.days} dias adicionados com sucesso'}

# ===================== DASHBOARD =====================

@api_router.get('/dashboard/stats')
async def get_dashboard_stats(current_user: dict = Depends(get_current_user)):
    db = await get_db()
    
    active_employees = await db.employees.count_documents({"status": "active"})
    total_epis = await db.epis.count_documents({})
    low_stock_count = await db.epis.count_documents({"$expr": {"$lte": ["$current_stock", "$min_stock"]}})
    
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    recent_deliveries = await db.deliveries.count_documents({
        "is_return": False,
        "created_at": {"$gte": thirty_days_ago}
    })
    
    # EPIs com validade próxima
    expiry_date = datetime.now(timezone.utc) + timedelta(days=30)
    expiring_count = await db.epis.count_documents({
        "$or": [
            {"validity_date": {"$ne": None, "$lte": expiry_date}},
            {"ca_validity": {"$ne": None, "$lte": expiry_date}}
        ]
    })
    
    return {
        'active_employees': active_employees,
        'total_epis': total_epis,
        'low_stock_count': low_stock_count,
        'recent_deliveries': recent_deliveries,
        'expiring_epis': expiring_count
    }

app.include_router(api_router)
