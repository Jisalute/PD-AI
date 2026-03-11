import os

import pymysql
from dotenv import load_dotenv


def get_mysql_config() -> dict:
	load_dotenv()

	def require_env(name: str) -> str:
		value = os.getenv(name)
		if not value:
			raise ValueError(f"Missing required env var: {name}")
		return value

	return {
		"host": require_env("MYSQL_HOST"),
		"port": int(require_env("MYSQL_PORT")),
		"user": require_env("MYSQL_USER"),
		"password": require_env("MYSQL_PASSWORD"),
		"database": require_env("MYSQL_DATABASE"),
		"charset": require_env("MYSQL_CHARSET") if os.getenv("MYSQL_CHARSET") else "utf8mb4",
		"autocommit": True,
	}


def get_mysql_config_without_db() -> dict:
	"""获取不指定数据库的配置（用于创建数据库）"""
	load_dotenv()

	def require_env(name: str) -> str:
		value = os.getenv(name)
		if not value:
			raise ValueError(f"Missing required env var: {name}")
		return value

	return {
		"host": require_env("MYSQL_HOST"),
		"port": int(require_env("MYSQL_PORT")),
		"user": require_env("MYSQL_USER"),
		"password": require_env("MYSQL_PASSWORD"),
		"charset": require_env("MYSQL_CHARSET") if os.getenv("MYSQL_CHARSET") else "utf8mb4",
		"autocommit": True,
	}


def create_database_if_not_exists():
	"""自动创建数据库（如果不存在）"""
	config = get_mysql_config_without_db()
	database_name = os.getenv("MYSQL_DATABASE")

	connection = pymysql.connect(**config)
	try:
		with connection.cursor() as cursor:
			cursor.execute(
				f"CREATE DATABASE IF NOT EXISTS {database_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
			print(f"数据库 '{database_name}' 检查/创建完成")
	finally:
		connection.close()


TABLE_STATEMENTS = [
	# ========== 原有表 ==========
	
	"""
	CREATE TABLE IF NOT EXISTS pd_users (
		id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
		name VARCHAR(64) NOT NULL COMMENT '姓名',
		account VARCHAR(64) NOT NULL UNIQUE COMMENT '账号',
		password_hash VARCHAR(255) NOT NULL COMMENT '密码哈希',
		role VARCHAR(32) NOT NULL COMMENT '角色',
		phone VARCHAR(32) COMMENT '手机号',
		email VARCHAR(128) COMMENT '邮箱',
		created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
		updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
		CHECK (role IN (
			'管理员',
			'大区经理',
			'自营库管理',
			'财务',
			'会计'
		))
	) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户表';
	""",
# ========== AI图片真伪检测引擎相关表 ==========
# 图片检测记录表
	"""
	CREATE TABLE IF NOT EXISTS pd_image_detection (
    	id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    	image_url VARCHAR(255) NOT NULL COMMENT '图片存储路径或URL',
    	image_md5 VARCHAR(32) NOT NULL COMMENT '图片MD5值，用于去重',
    	upload_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '上传时间',
    	detection_status TINYINT DEFAULT 0 COMMENT '检测状态：0-待检测，1-检测中，2-已完成',
    	net_weight_area TEXT COMMENT '净重区域坐标信息',
    	detection_result TINYINT DEFAULT 0 COMMENT '检测结果：0-正常，1-可疑，2-篡改',
    	confidence_score FLOAT DEFAULT 0 COMMENT '模型置信度',
    	anomaly_type VARCHAR(50) COMMENT '异常类型',
    	anomaly_area_image VARCHAR(255) COMMENT '异常区域截图路径',
    	detection_time DATETIME COMMENT '检测完成时间',
    	reviewer_id BIGINT COMMENT '复核人ID',
    	review_status TINYINT DEFAULT 0 COMMENT '复核状态：0-未复核，1-已复核',
    	review_time DATETIME COMMENT '复核时间',
    	review_remark VARCHAR(255) COMMENT '复核备注',
    	is_used_for_train TINYINT DEFAULT 0 COMMENT '是否已用于模型训练',
    	created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    	updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    	INDEX idx_md5 (image_md5),
    	INDEX idx_status (detection_status),
    	INDEX idx_result (detection_result),
    	INDEX idx_review_status (review_status)
	) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='图片检测记录表';
	""",
	# 人工抽查记录表
	"""
	CREATE TABLE IF NOT EXISTS pd_sample_check (
    	id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    	check_time DATETIME NOT NULL COMMENT '抽查时间',
    	checker_id BIGINT NOT NULL COMMENT '抽查人ID',
    	detection_record_id BIGINT NOT NULL COMMENT '关联的检测记录ID',
    	original_result TINYINT NOT NULL COMMENT '原始检测结果',
    	check_result TINYINT NOT NULL COMMENT '抽查确认结果',
    	is_match TINYINT DEFAULT 1 COMMENT '是否一致',
    	remark VARCHAR(255) COMMENT '抽查备注',
    	created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    	INDEX idx_checker (checker_id),
    	INDEX idx_detection (detection_record_id)
	) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='人工抽查记录表';
	""",
	# 检测日志表
	"""
	CREATE TABLE IF NOT EXISTS pd_detection_log (
    	id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    	record_id BIGINT NOT NULL COMMENT '关联的检测记录ID',
    	log_level VARCHAR(20) DEFAULT 'info' COMMENT '日志级别',
    	log_content TEXT NOT NULL COMMENT '日志内容',
    	create_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    	INDEX idx_record (record_id)
	) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='检测日志表';
	""",
]


def create_tables() -> None:
	# 第1步：先创建数据库（如果不存在）
	create_database_if_not_exists()

	# 第2步：创建表
	config = get_mysql_config()
	connection = pymysql.connect(**config)
	try:
		with connection.cursor() as cursor:
			for statement in TABLE_STATEMENTS:
				cursor.execute(statement)
		print("所有数据表创建完成")
	finally:
		connection.close()


if __name__ == "__main__":
	create_tables()