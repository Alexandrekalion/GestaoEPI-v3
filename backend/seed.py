from database import get_db
from auth import get_password_hash
from datetime import datetime, timedelta, timezone
import asyncio
import logging

logger = logging.getLogger(__name__)

async def seed_database():
    db = await get_db()
    
    # Criar admin (substitui super_admin)
    existing_user = await db.users.find_one({"username": "administrador"})
    if not existing_user:
        admin = {
            "username": "administrador",
            "email": "admin@cipolatti.com",
            "hashed_password": get_password_hash("LR1a2b3c4567@"),
            "role": "admin",  # Novo perfil
            "must_change_password": True,
            "is_active": True,
            "password_changed_at": datetime.now(timezone.utc),
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }
        await db.users.insert_one(admin)
        logger.info("Administrador criado: administrador")
    else:
        # Atualizar perfil para o novo sistema
        if existing_user.get('role') in ['super_admin', 'admin']:
            await db.users.update_one(
                {"_id": existing_user['_id']},
                {"$set": {"role": "admin"}}
            )
    
    # Criar licença
    existing_license = await db.panel_license.find_one({})
    if not existing_license:
        license_doc = {
            "expires_at": datetime.now(timezone.utc) + timedelta(days=30),
            "is_blocked": False,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }
        await db.panel_license.insert_one(license_doc)
        logger.info("Licença do painel criada: 30 dias")
    
    logger.info("Seed concluído com sucesso")

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed_database())
