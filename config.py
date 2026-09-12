import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Configuration for the application."""
    
    # Flask configuration
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # Database configuration
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///cms.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Application settings
    DEFAULT_DUE_DAYS = 30
    INVOICE_PREFIX = 'INV-'