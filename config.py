import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_NAME = os.getenv('DB_NAME', 'stat')
    DB_USER = os.getenv('DB_USER', 'postgres')
    DB_PASSWORD = os.getenv('DB_PASSWORD', 'admin')
    DB_PORT = os.getenv('DB_PORT', '5432')

    AUTH_USERNAME = os.getenv('AUTH_USERNAME', 'admin')
    AUTH_PASSWORD = os.getenv('AUTH_PASSWORD', 'adminis')
    SECRET_KEY = os.getenv('SECRET_KEY', 'HSioe820_yew78')

    # Production settings
    # DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
    # HOST = os.getenv('HOST', '0.0.0.0')
    # PORT = int(os.getenv('PORT', 8000))

    DEBUG = os.getenv('DEBUG', 'True')
    HOST = os.getenv('HOST', '127.0.0.1')
    PORT = int(os.getenv('PORT', 8000))

    @property
    def db_config(self):
        return {
            'host': self.DB_HOST,
            'database': self.DB_NAME,
            'user': self.DB_USER,
            'password': self.DB_PASSWORD,
            'port': self.DB_PORT
        }


config = Config()
