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
	CREATE TABLE IF NOT EXISTS pd_summary (
		id BIGINT AUTO_INCREMENT PRIMARY KEY,
		contract_no VARCHAR(64) NOT NULL,
		report_date DATE,
		driver_phone VARCHAR(32),
		driver_name VARCHAR(64),
		vehicle_no VARCHAR(32),
		product_name VARCHAR(64),
		weigh_date DATE,
		weigh_ticket_no VARCHAR(64),
		net_weight DECIMAL(12, 3),
		unit_price DECIMAL(12, 2),
		amount DECIMAL(14, 2),
		planned_truck_count INT,
		shipper VARCHAR(64),
		payee VARCHAR(64),
		other_fees DECIMAL(14, 2),
		amount_payable DECIMAL(14, 2),
		payment_schedule_date DATE,
		remarks TEXT,
		remittance_unit_price DECIMAL(12, 2),
		remittance_amount DECIMAL(14, 2),
		received_payment_date DATE,
		arrival_payment_90 DECIMAL(14, 2),
		final_payment_date DATE,
		final_payment_10 DECIMAL(14, 2),
		payout_date DATE,
		payout_details TEXT,
		created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
		updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
	) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
	""",
	"""
	CREATE TABLE IF NOT EXISTS pd_users (
		id BIGINT AUTO_INCREMENT PRIMARY KEY,
		name VARCHAR(64) NOT NULL,
		account VARCHAR(64) NOT NULL UNIQUE,
		password_hash VARCHAR(255) NOT NULL,
		role VARCHAR(32) NOT NULL,
		phone VARCHAR(32),
		email VARCHAR(128),
		created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
		updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
		CHECK (role IN (
			'管理员',
			'大区经理',
			'自营库管理',
			'财务',
			'会计'
		))
	) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
	""",
	"""
	CREATE TABLE IF NOT EXISTS pd_customers (
		id BIGINT AUTO_INCREMENT PRIMARY KEY,
		smelter_name VARCHAR(128) NOT NULL,
		address VARCHAR(255),
		contact_person VARCHAR(64),
		contact_phone VARCHAR(32),
		contact_address VARCHAR(255) COMMENT '联系人地址',
		created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
		updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
	) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
	""",
	"""
	CREATE TABLE IF NOT EXISTS pd_deliveries (
		id BIGINT AUTO_INCREMENT PRIMARY KEY,
		report_date DATE COMMENT '报货日期',
		delivery_time DATETIME COMMENT '送货时间',
		warehouse VARCHAR(64) COMMENT '送货库房',
		target_factory_id BIGINT COMMENT '目标工厂ID（关联pd_customers）',
		target_factory_name VARCHAR(128) COMMENT '目标工厂名称',
		product_name VARCHAR(64) COMMENT '货物品种',
		quantity DECIMAL(12, 3) COMMENT '数量（吨）',
		vehicle_no VARCHAR(32) COMMENT '车牌号',
		driver_name VARCHAR(64) COMMENT '司机姓名',
		driver_phone VARCHAR(32) COMMENT '司机电话',
		driver_id_card VARCHAR(18) COMMENT '司机身份证号',
		has_delivery_order ENUM('有', '无') DEFAULT '无' COMMENT '是否有联单',
		delivery_order_image VARCHAR(255) COMMENT '联单图片路径',
		source_type ENUM('司机', '公司') DEFAULT '公司' COMMENT '来源：司机/公司',
		shipper VARCHAR(64) COMMENT '发货人（默认操作人）',
		payee VARCHAR(64) COMMENT '收款人',
		service_fee DECIMAL(14, 2) DEFAULT 0 COMMENT '服务费',
		contract_no VARCHAR(64) COMMENT '关联合同编号',
		contract_unit_price DECIMAL(12, 2) COMMENT '合同单价',
		total_amount DECIMAL(14, 2) COMMENT '总价（单价×数量）',
		status VARCHAR(32) DEFAULT '待确认' COMMENT '状态：待确认/已确认/已完成/已取消',
		created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
		updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
		INDEX idx_report_date (report_date),
		INDEX idx_contract_no (contract_no),
		INDEX idx_target_factory (target_factory_id),
		INDEX idx_vehicle_no (vehicle_no),
		INDEX idx_status (status)
	) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='销售台账/报货订单';
	""",
	"""
	CREATE TABLE IF NOT EXISTS pd_weighbills (
		id BIGINT AUTO_INCREMENT PRIMARY KEY,
		weigh_date DATE COMMENT '磅单日期',
		weigh_ticket_no VARCHAR(64) COMMENT '过磅单号',
		contract_no VARCHAR(64) COMMENT '合同编号（OCR识别）',
		delivery_id BIGINT COMMENT '关联的报货订单ID（通过日期+车牌匹配）',
		vehicle_no VARCHAR(32) COMMENT '车牌号',
		product_name VARCHAR(64) COMMENT '货物名称',
		gross_weight DECIMAL(12, 3) COMMENT '毛重（吨）',
		tare_weight DECIMAL(12, 3) COMMENT '皮重（吨）',
		net_weight DECIMAL(12, 3) COMMENT '净重（吨）',
		unit_price DECIMAL(12, 2) COMMENT '合同单价',
		total_amount DECIMAL(14, 2) COMMENT '总价（净重×单价）',
		weighbill_image VARCHAR(255) COMMENT '磅单图片路径',
		ocr_status VARCHAR(32) DEFAULT '待确认' COMMENT 'OCR状态：待确认/已确认/已修正',
		ocr_raw_data TEXT COMMENT 'OCR原始识别文本',
		is_manual_corrected TINYINT DEFAULT 0 COMMENT '是否人工修正',
		created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
		updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
		INDEX idx_weigh_date (weigh_date),
		INDEX idx_vehicle_no (vehicle_no),
		INDEX idx_contract_no (contract_no),
		INDEX idx_delivery_id (delivery_id),
		INDEX idx_status (ocr_status)
	) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='磅单表';
	""",
	"""
	CREATE TABLE IF NOT EXISTS pd_weighbill_settlements (
		id BIGINT AUTO_INCREMENT PRIMARY KEY,
		payable_amount DECIMAL(14, 2),
		created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
		updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
	) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
	""",
	"""
	CREATE TABLE IF NOT EXISTS pd_receipts (
		id BIGINT AUTO_INCREMENT PRIMARY KEY,
		remittance_amount DECIMAL(14, 2),
		received_payment_date DATE,
		arrival_payment_90 DECIMAL(14, 2),
		final_payment_date DATE,
		final_payment_10 DECIMAL(14, 2),
		created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
		updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
	) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
	""",
	"""
	CREATE TABLE IF NOT EXISTS pd_payout_details (
		id BIGINT AUTO_INCREMENT PRIMARY KEY,
		payout_amount DECIMAL(14, 2),
		payout_details TEXT,
		created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
		updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
	) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
	""",

	# ========== 新增合同管理表 ==========
	"""
	CREATE TABLE IF NOT EXISTS pd_contracts (
		id BIGINT AUTO_INCREMENT PRIMARY KEY,
		seq_no INT UNIQUE COMMENT '序号（自动生成，使用触发器或应用层生成）',
		contract_no VARCHAR(64) NOT NULL UNIQUE COMMENT '合同编号',
		contract_date DATE COMMENT '合同签订日期',
		end_date DATE COMMENT '合同截止日期',
		smelter_company VARCHAR(128) COMMENT '冶炼公司',
		total_quantity DECIMAL(12, 3) COMMENT '合同总数量（吨）',
		arrival_payment_ratio DECIMAL(5, 4) DEFAULT 0.9 COMMENT '到货款比例',
		final_payment_ratio DECIMAL(5, 4) DEFAULT 0.1 COMMENT '尾款比例',
		contract_image_path VARCHAR(255) COMMENT '合同图片路径',
		status VARCHAR(32) DEFAULT '生效中' COMMENT '状态：生效中/已到期/已终止',
		remarks TEXT COMMENT '备注',
		created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
		updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
		INDEX idx_seq_no (seq_no)
	) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
	""",
	"""
	CREATE TABLE IF NOT EXISTS pd_contract_products (
		id BIGINT AUTO_INCREMENT PRIMARY KEY,
		contract_id BIGINT NOT NULL COMMENT '合同ID',
		product_name VARCHAR(64) NOT NULL COMMENT '品种名称',
		unit_price DECIMAL(12, 2) COMMENT '单价（元）',
		sort_order INT DEFAULT 0 COMMENT '排序',
		created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
		FOREIGN KEY (contract_id) REFERENCES pd_contracts(id) ON DELETE CASCADE,
		INDEX idx_contract_id (contract_id)
	) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
	""",
	# 磅单结余管理
	"""
	CREATE TABLE IF NOT EXISTS pd_payment_receipts (
		id BIGINT AUTO_INCREMENT PRIMARY KEY,
		receipt_no VARCHAR(64) COMMENT '银行回单流水号',
		receipt_image VARCHAR(255) NOT NULL COMMENT '回单图片存储路径',
		payment_date DATE NOT NULL COMMENT '支付日期',
		payment_time TIME COMMENT '支付时间',
		payer_name VARCHAR(64) COMMENT '付款人姓名',
		payer_account VARCHAR(32) COMMENT '付款账号',
		payee_name VARCHAR(64) NOT NULL COMMENT '收款人姓名（司机）',
		payee_account VARCHAR(32) COMMENT '收款账号',
		amount DECIMAL(14, 2) NOT NULL COMMENT '支付金额',
		bank_name VARCHAR(64) COMMENT '银行名称',
		remark VARCHAR(255) COMMENT '备注/用途',
		ocr_status TINYINT DEFAULT 0 COMMENT '0=待确认, 1=已确认, 2=已核销',
		is_manual_corrected TINYINT DEFAULT 0 COMMENT '0=自动, 1=人工修正',
		ocr_raw_data TEXT COMMENT 'OCR原始识别文本',
		created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
		updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
		INDEX idx_payee_amount (payee_name, amount),
		INDEX idx_payment_date (payment_date),
		INDEX idx_ocr_status (ocr_status)
	) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='支付回单表';
	""",
	"""
	CREATE TABLE IF NOT EXISTS pd_balance_details (
		id BIGINT AUTO_INCREMENT PRIMARY KEY,
		contract_no VARCHAR(64) COMMENT '合同编号',
		delivery_id BIGINT COMMENT '报货订单ID',
		weighbill_id BIGINT NOT NULL COMMENT '磅单ID',
		driver_name VARCHAR(64) COMMENT '司机姓名',
		driver_phone VARCHAR(32) COMMENT '司机电话',
		vehicle_no VARCHAR(32) COMMENT '车牌号',
		payable_amount DECIMAL(14, 2) NOT NULL COMMENT '应付金额',
		paid_amount DECIMAL(14, 2) DEFAULT 0 COMMENT '已支付金额',
		balance_amount DECIMAL(14, 2) COMMENT '结余金额',
		payment_status TINYINT DEFAULT 0 COMMENT '0=待支付, 1=部分支付, 2=已结清',
		created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
		updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
		UNIQUE KEY uk_weighbill (weighbill_id),
		INDEX idx_contract_no (contract_no),
		INDEX idx_driver_name (driver_name),
		INDEX idx_payment_status (payment_status),
		INDEX idx_created_at (created_at)
	) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='磅单结余明细表';
	""",
	"""
	CREATE TABLE IF NOT EXISTS pd_receipt_settlements (
		id BIGINT AUTO_INCREMENT PRIMARY KEY,
		receipt_id BIGINT NOT NULL COMMENT '支付回单ID',
		balance_id BIGINT NOT NULL COMMENT '结余明细ID',
		settled_amount DECIMAL(14, 2) COMMENT '本次核销金额',
		created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
		UNIQUE KEY uk_receipt_balance (receipt_id, balance_id),
		INDEX idx_receipt_id (receipt_id),
		INDEX idx_balance_id (balance_id)
	) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='支付回单与结余核销关联表';
	""",
	# ========== 新增表 ==========
	 """
    CREATE TABLE IF NOT EXISTS t_prediction_result (
        predict_id        BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '预测ID',
        biz_date          DATE NOT NULL COMMENT '预测日期',
        category_code     VARCHAR(50) NOT NULL COMMENT '品类代码',
        predicted_value   DECIMAL(18, 2) NOT NULL COMMENT '预测配运量',
        rec_interval_start DATETIME COMMENT '推荐收货开始时间',
        rec_interval_end   DATETIME COMMENT '推荐收货结束时间',
        status            TINYINT DEFAULT 1 COMMENT '状态: 1-有效, 0-已覆盖/作废',
        adjust_reason     VARCHAR(255) COMMENT '人工调整原因',
        adjusted_value    DECIMAL(18, 2) COMMENT '调整后数值(若为空则为原始预测)',
        operator          VARCHAR(50) COMMENT '最后操作人',
        create_time       DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
        update_time       DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        INDEX idx_date_category (biz_date, category_code),
        INDEX idx_status (status)
    ) COMMENT='预测结果表';
    """,
    """
    CREATE TABLE IF NOT EXISTS t_price_alert (
        alert_id          BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '预警ID',
        rule_id           VARCHAR(50) NOT NULL COMMENT '触发规则ID',
        rule_name         VARCHAR(100) COMMENT '规则名称快照',
        category_code     VARCHAR(50) NOT NULL COMMENT '关联品类',
        current_price     DECIMAL(18, 4) NOT NULL COMMENT '触发时的当前价格',
        threshold_value   DECIMAL(18, 4) COMMENT '触发阈值',
        trigger_reason    VARCHAR(255) COMMENT '触发具体原因描述',
        level             TINYINT COMMENT '预警级别: 1-低, 2-中, 3-高',
        status            TINYINT DEFAULT 0 COMMENT '状态: 0-未确认, 1-已确认, 2-已关闭',
        confirm_user      VARCHAR(50) COMMENT '确认人',
        confirm_time      DATETIME COMMENT '确认时间',
        create_time       DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '触发时间',
        INDEX idx_category_status (category_code, status),
        INDEX idx_create_time (create_time)
    ) COMMENT='价格预警记录表';
    """,
    """
    CREATE TABLE IF NOT EXISTS t_supply_anomaly (
        anomaly_id        BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '异常ID',
        category_code     VARCHAR(50) NOT NULL COMMENT '受影响品类',
        supplier_code     VARCHAR(50) NOT NULL COMMENT '供应商代码',
        supplier_name     VARCHAR(100) COMMENT '供应商名称',
        anomaly_type      VARCHAR(50) COMMENT '异常类型: 断供/延迟/质量等',
        description       TEXT COMMENT '异常详细描述',
        impact_scope      VARCHAR(255) COMMENT '影响范围描述',
        duration_days     INT COMMENT '预计持续天数',
        status            TINYINT DEFAULT 0 COMMENT '处理状态: 0-待处理, 1-处理中, 2-已解决',
        recommended_actions JSON COMMENT '推荐应对动作列表(JSON格式)',
        handler           VARCHAR(50) COMMENT '当前处理人',
        create_time       DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '发现时间',
        resolve_time      DATETIME COMMENT '解决时间',
        INDEX idx_supplier_status (supplier_code, status),
        INDEX idx_category (category_code)
    ) COMMENT='供应异常记录表';
    """,
    """
    CREATE TABLE IF NOT EXISTS t_allocation_plan (
        plan_id           BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '方案ID',
        biz_date          DATE NOT NULL COMMENT '执行日期',
        category_range    VARCHAR(255) COMMENT '适用品类范围',
        plan_details      JSON NOT NULL COMMENT '方案详情: 包含各仓库分配量、物流指令等(JSON)',
        input_factors     JSON COMMENT '输入因素快照: 库存/合同/成本等',
        expected_kpi      JSON COMMENT '预期KPI评估: 成本/时效/满意度',
        status            TINYINT DEFAULT 0 COMMENT '状态: 0-草稿, 1-已发布, 2-执行中, 3-已完成, 4-已取消',
        creator           VARCHAR(50) COMMENT '创建人/生成算法版本',
        create_time       DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '生成时间',
        execute_log       TEXT COMMENT '执行日志摘要',
        INDEX idx_date_status (biz_date, status),
        INDEX idx_creator (creator)
    ) COMMENT='动态分配方案表';
    """,# ========== AI图片真伪检测引擎相关表 ==========
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