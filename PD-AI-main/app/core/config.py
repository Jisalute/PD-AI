import os

from dotenv import load_dotenv
from pydantic import BaseModel
from typing import Optional


def load_settings() -> "Settings":
    load_dotenv()
    return Settings(
        app_name=os.getenv("APP_NAME", "PD API"),
        jwt_secret=os.getenv("JWT_SECRET", "change-me"),
        jwt_algorithm=os.getenv("JWT_ALGORITHM", "HS256"),
        db_url=os.getenv(
            "DATABASE_URL", "mysql+pymysql://user:pass@localhost:3306/pd"
        ),

        wechat_app_id=os.getenv("WECHAT_APP_ID", ""),
        wechat_app_secret=os.getenv("WECHAT_APP_SECRET", ""),

        coze_api_token=os.getenv("COZE_API_TOKEN", ""),
        coze_bot_url=os.getenv("COZE_BOT_URL", ""),
        coze_project_id=os.getenv("COZE_PROJECT_ID", ""),
    )


class Settings(BaseModel):

    app_name: str
    jwt_secret: str
    jwt_algorithm: str
    db_url: str


    wechat_app_id: str = ""
    wechat_app_secret: str = ""


    coze_api_token: str = ""
    coze_bot_url: str = ""
    coze_project_id: str = ""


settings = load_settings()