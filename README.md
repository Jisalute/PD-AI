# PD 认证服务

本仓库仅保留了 “PD” 用户认证模块，其他业务已移除。

## 主要组成

* `main.py` – 应用入口，注册认证路由并启动 FastAPI。
* `services/pd_auth_service.py` – 对外导出认证相关类/函数。
* `app/services/user_services.py` – 用户 CRUD 与登录逻辑。
* `app/api/v1/user/routes.py` – FastAPI 路由。
* `core/` – 公共工具：数据库、JWT、日志等。
* `database_setup.py` – 建立 `pd_users` 表。
* `.env` – 配置环境变量。

## 快速开始

1. 创建虚拟环境并安装依赖：
   ```bash
   uv venv
   uv sync
   ```

2. 编辑 `.env`：
   ```ini
   APP_NAME=PD API
   JWT_SECRET=change-me
   JWT_ALGORITHM=HS256

   MYSQL_HOST=127.0.0.1
   MYSQL_PORT=3306
   MYSQL_USER=root
   MYSQL_PASSWORD=123456
   MYSQL_DATABASE=PD_db
   MYSQL_CHARSET=utf8mb4

   DATABASE_URL=mysql+pymysql://root:123456@127.0.0.1:3306/PD_db?charset=utf8mb4
   ```

3. 初始化数据库：
   ```bash
   python database_setup.py
   ```

4. 启动服务：
   ```bash
   uv run main.py            # 开发模式
   # 或
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

5. 查看文档：`http://localhost:8000/docs`

## 提供的接口

* `GET /healthz` – 健康检查
* `GET /init-db` – 手动建立/同步用户表

### 认证相关

* `POST /api/v1/user/auth/login` – 登录并获取 JWT
* `POST /api/v1/user/auth/logout` – 登出
* `POST /api/v1/user/auth/refresh` – 刷新令牌
* `GET /api/v1/user/me` – 当前用户信息
* `/api/v1/user/users` 下的用户 CRUD（需管理员权限）


## AI 图片真伪检测（可选插件）

如果启用了相应模型 API，可以使用以下接口上传图片并执行真伪检测：

* `POST /api/v1/upload` – 上传图片并自动/手动触发检测
* `GET  /api/v1/records` – 分页查询检测记录
* `GET  /api/v1/records/{record_id}` – 查询单条检测详情
* `PUT  /api/v1/records/review` – 提交人工复核结果

启动时会在数据库中创建 `pd_image_detection`、`pd_detection_log` 等表。

---

详情见 Swagger 文档或源码。

---

这是一个最小化的认证服务，可作为其他系统的认证后端；如需增加业务，
只需添加相应路由并在 `main.py` 注册即可。
