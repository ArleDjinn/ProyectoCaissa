# services/guardians.py
from ..models import Guardian, User, Child, KnowledgeLevel
from ..extensions import db
from datetime import date

# -------- Guardian --------
def create_guardian(user: User, phone: str, allow_whatsapp_group: bool = False) -> Guardian:
    guardian = Guardian(user=user, phone=phone, allow_whatsapp_group=allow_whatsapp_group)
    db.session.add(guardian)
    return guardian

def get_guardian_by_user(user: User) -> Guardian:
    return Guardian.query.filter_by(user_id=user.id).first()

def update_guardian(guardian: Guardian, phone: str = None, allow_whatsapp_group: bool = None) -> Guardian:
    if phone is not None:
        guardian.phone = phone
    if allow_whatsapp_group is not None:
        guardian.allow_whatsapp_group = allow_whatsapp_group
    return guardian

def delete_guardian(guardian: Guardian):
    db.session.delete(guardian)

# -------- Child --------
def create_child(guardian: Guardian, name: str, birthdate: date = None,
                 knowledge_level: KnowledgeLevel = None,
                 health_info: str = None,
                 allow_media: bool = False) -> Child:
    child = Child(
        guardian=guardian,
        name=name,
        birthdate=birthdate,
        knowledge_level=knowledge_level,
        health_info=health_info,
        allow_media=allow_media,
    )
    db.session.add(child)
    return child

def get_children_by_guardian(guardian: Guardian):
    return Child.query.filter_by(guardian_id=guardian.id).all()

def update_child(child: Child, name: str = None, birthdate: date = None,
                 knowledge_level: KnowledgeLevel = None,
                 health_info: str = None,
                 allow_media: bool = None) -> Child:
    if name is not None:
        child.name = name
    if birthdate is not None:
        child.birthdate = birthdate
    if knowledge_level is not None:
        child.knowledge_level = knowledge_level
    if health_info is not None:
        child.health_info = health_info
    if allow_media is not None:
        child.allow_media = allow_media
    return child

def delete_child(child: Child):
    db.session.delete(child)
