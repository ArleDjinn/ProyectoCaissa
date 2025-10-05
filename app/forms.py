from flask_wtf import FlaskForm
from wtforms import (
    Form,
    StringField,
    PasswordField,
    IntegerField,
    BooleanField,
    TimeField,
    SelectField,
    SubmitField,
    SelectMultipleField,
    FieldList,
    FormField,
    HiddenField,
)
from wtforms.fields import DateField
from wtforms.validators import (
    DataRequired,
    Email,
    NumberRange,
    Optional,
    EqualTo,
    Length,
    Regexp,
)
from .models import DayOfWeek, KnowledgeLevel, PaymentMethod

class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Contraseña", validators=[DataRequired()])
    submit = SubmitField("Ingresar")

class PlanForm(FlaskForm):
    name = StringField("Nombre", validators=[DataRequired()])
    max_children = IntegerField("Máx. niños", validators=[DataRequired(), NumberRange(min=1)])
    max_workshops_per_child = IntegerField("Talleres por niño", validators=[DataRequired(), NumberRange(min=1)])
    price_monthly = IntegerField("Precio mensual (CLP)", validators=[DataRequired()])
    quarterly_discount_pct = IntegerField(
        "Descuento trimestral (%)",
        validators=[DataRequired(), NumberRange(min=0, max=100)],
        default=15,
    )
    is_active = BooleanField("Activo")
    submit = SubmitField("Guardar")

class WorkshopForm(FlaskForm):
    name = StringField("Nombre", validators=[DataRequired()])
    day_of_week = SelectField("Día", choices=[(d.name, d.value) for d in DayOfWeek], validators=[DataRequired()])
    start_time = TimeField("Hora inicio", validators=[DataRequired()])
    end_time = TimeField("Hora fin")
    is_active = BooleanField("Activo")
    submit = SubmitField("Guardar")

# --- Subformulario para hijos ---
class ChildForm(Form):
    name = StringField("Nombre del niño/a", validators=[Optional()])
    birthdate = DateField("Fecha de nacimiento", format="%Y-%m-%d", validators=[Optional()])
    knowledge_level = SelectField(
        "Nivel de ajedrez",
        choices=[(k.name, k.value) for k in KnowledgeLevel],
        validators=[Optional()]
    )
    health_info = StringField("Información médica relevante", validators=[Optional()])
    allow_media = BooleanField("Autorizo uso de material audiovisual")


PHONE_REGEXP = r"^\+?\d{7,15}$"


class GuardianAdminForm(FlaskForm):
    name = StringField("Nombre", validators=[DataRequired()])
    email = StringField("Correo electrónico", validators=[DataRequired(), Email()])
    phone = StringField(
        "Teléfono",
        validators=[DataRequired(), Regexp(PHONE_REGEXP, message="Ingresa un teléfono válido (7 a 15 dígitos, opcional +).")],
    )
    allow_whatsapp_group = BooleanField("Autoriza grupo de WhatsApp")
    submit = SubmitField("Guardar cambios")


class ChildAdminForm(FlaskForm):
    child_id = HiddenField()
    name = StringField("Nombre", validators=[DataRequired()])
    birthdate = DateField("Fecha de nacimiento", format="%Y-%m-%d", validators=[Optional()])
    knowledge_level = SelectField("Nivel de ajedrez", validators=[Optional()])
    health_info = StringField("Información médica relevante", validators=[Optional()])
    allow_media = BooleanField("Autorizo uso de material audiovisual")
    submit = SubmitField("Guardar")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.knowledge_level.choices = [("", "Sin especificar")] + [
            (k.name, k.value) for k in KnowledgeLevel
        ]


class DeleteChildForm(FlaskForm):
    child_id = HiddenField(validators=[DataRequired()])
    submit = SubmitField("Eliminar")


class MoveEnrollmentForm(FlaskForm):
    enrollment_id = HiddenField(validators=[DataRequired()])
    new_workshop_id = SelectField("Nuevo taller", coerce=int, validators=[DataRequired()])
    submit = SubmitField("Mover matrícula")


class CancelEnrollmentForm(FlaskForm):
    enrollment_id = HiddenField(validators=[DataRequired()])
    submit = SubmitField("Cancelar matrícula")


class SimpleCSRFForm(FlaskForm):
    submit = SubmitField()

class InscriptionForm(FlaskForm):
    guardian_name = StringField("Nombre del apoderado", validators=[DataRequired()])
    guardian_email = StringField("Correo electrónico", validators=[DataRequired(), Email()])
    phone = StringField(
        "Teléfono",
        validators=[DataRequired(), Regexp(PHONE_REGEXP, message="Ingresa un teléfono válido (7 a 15 dígitos, opcional +).")],
    )
    allow_whatsapp_group = BooleanField("Autorizo unirme al grupo de WhatsApp de apoderados")

    children = FieldList(FormField(ChildForm))

    payment_method = SelectField("Método de pago",
                                 choices=[
                                     (PaymentMethod.in_person.name, "Pago presencial"),
                                     (PaymentMethod.transfer.name, "Transferencia bancaria"),
                                     (PaymentMethod.webpay.name, "Webpay")
                                 ],
                                 validators=[DataRequired()]
                                 )

    workshops = SelectMultipleField("Talleres", coerce=int, validators=[DataRequired()])

    submit = SubmitField("Inscribir")

class InitialPasswordForm(FlaskForm):
    password = PasswordField(
        "Nueva contraseña",
        validators=[DataRequired(), Length(min=8, message="Debe tener al menos 8 caracteres.")],
    )
    confirm_password = PasswordField(
        "Confirmar contraseña",
        validators=[
            DataRequired(),
            EqualTo("password", message="Las contraseñas deben coincidir."),
        ],
    )
    submit = SubmitField("Guardar contraseña")

class PasswordResetRequestForm(FlaskForm):
    email = StringField("Correo electrónico", validators=[DataRequired(), Email()])
    submit = SubmitField("Enviar instrucciones")


class PasswordResetForm(FlaskForm):
    password = PasswordField(
        "Nueva contraseña",
        validators=[DataRequired(), Length(min=8, message="Debe tener al menos 8 caracteres.")],
    )
    confirm_password = PasswordField(
        "Confirmar contraseña",
        validators=[
            DataRequired(),
            EqualTo("password", message="Las contraseñas deben coincidir."),
        ],
    )
    submit = SubmitField("Actualizar contraseña")