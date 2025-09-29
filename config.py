import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(BASE_DIR, "app.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Webpay
    TBK_ENV = os.environ.get("TBK_ENV", "integration")
    TBK_COMMERCE_CODE = os.environ.get("TBK_COMMERCE_CODE")
    TBK_API_KEY = os.environ.get("TBK_API_KEY")