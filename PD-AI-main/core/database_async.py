# core/database_async.py
import aiomysql
from typing import Optional, AsyncGenerator
from contextlib import asynccontextmanager
import os
from dotenv import load_dotenv

load_dotenv()


class DatabaseAsync:
    def __init__(self):
        self.pool: Optional[aiomysql.Pool] = None

    async def init_pool(self):
        """初始化连接池"""
        if not self.pool:
            self.pool = await aiomysql.create_pool(
                host=os.getenv("MYSQL_HOST", "localhost"),
                port=int(os.getenv("MYSQL_PORT", "3306")),
                user=os.getenv("MYSQL_USER", "root"),
                password=os.getenv("MYSQL_PASSWORD", ""),
                db=os.getenv("MYSQL_DATABASE", "pd_ai"),
                charset=os.getenv("MYSQL_CHARSET", "utf8mb4"),
                autocommit=True,
                minsize=1,
                maxsize=10
            )
        return self.pool

    async def close(self):
        """关闭连接池"""
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()
            self.pool = None

    @asynccontextmanager
    async def get_connection(self) -> AsyncGenerator[aiomysql.Connection, None]:
        """获取数据库连接"""
        pool = await self.init_pool()
        async with pool.acquire() as conn:
            yield conn

    @asynccontextmanager
    async def get_cursor(self, cursor_type=aiomysql.DictCursor):
        """获取数据库游标"""
        async with self.get_connection() as conn:
            async with conn.cursor(cursor_type) as cursor:
                yield cursor


# 创建单例
db_async = DatabaseAsync()