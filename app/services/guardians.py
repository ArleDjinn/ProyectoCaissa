# services/guardians.py
from datetime import date

from ..extensions import db
from ..models import Child, Guardian, KnowledgeLevel, User

# -------- Guardian --------
def create_guardian(user: User, phone: str, allow_whatsapp_group: bool = False) -> Guardian:
    guardian = Guardian(user=user, phone=phone, allow_whatsapp_group=allow_whatsapp_group)
    db.session.add(guardian)
    return guardian

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
