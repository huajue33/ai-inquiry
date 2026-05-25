-- 性能优化索引（MySQL 8.0）
-- 执行方式：docker compose exec mysql mysql -uroot -p$DB_PASSWORD quotation < /path/to/this.sql

DELIMITER $$

DROP PROCEDURE IF EXISTS add_index_if_not_exists$$

CREATE PROCEDURE add_index_if_not_exists(
    IN p_table VARCHAR(128),
    IN p_index VARCHAR(128),
    IN p_sql TEXT
)
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = p_table
          AND INDEX_NAME = p_index
        LIMIT 1
    ) THEN
        SET @stmt = p_sql;
        PREPARE s FROM @stmt;
        EXECUTE s;
        DEALLOCATE PREPARE s;
    END IF;
END$$

DELIMITER ;

-- ===== prices 表 =====

-- 最新价格查询：ORDER BY price_date DESC LIMIT 1
CALL add_index_if_not_exists('prices', 'idx_prices_product_date',
    'CREATE INDEX idx_prices_product_date ON prices (product_id, price_date DESC)');

-- 涨跌排行：按日期取所有产品价格，覆盖 price_value 避免回表
CALL add_index_if_not_exists('prices', 'idx_prices_date_product',
    'CREATE INDEX idx_prices_date_product ON prices (price_date, product_id, price_value)');

-- ===== conversations 表 =====

-- 用户对话列表：WHERE user_id=? AND is_deleted=0 ORDER BY updated_at DESC
CALL add_index_if_not_exists('conversations', 'idx_conversations_user_active',
    'CREATE INDEX idx_conversations_user_active ON conversations (user_id, is_deleted, updated_at DESC)');

-- ===== chat_messages 表 =====

-- 对话消息加载：WHERE conversation_id=? ORDER BY created_at
CALL add_index_if_not_exists('chat_messages', 'idx_messages_conv_time',
    'CREATE INDEX idx_messages_conv_time ON chat_messages (conversation_id, created_at)');

-- ===== products 表 =====

-- 分类筛选
CALL add_index_if_not_exists('products', 'idx_products_category',
    'CREATE INDEX idx_products_category ON products (category_id)');

-- 模糊搜索降级（前缀索引）
CALL add_index_if_not_exists('products', 'idx_products_basename',
    'CREATE INDEX idx_products_basename ON products (base_name(100))');

-- ===== categories 表 =====

-- 子分类展开查询
CALL add_index_if_not_exists('categories', 'idx_categories_parent_level',
    'CREATE INDEX idx_categories_parent_level ON categories (parent_id, level)');

-- 清理
DROP PROCEDURE IF EXISTS add_index_if_not_exists;
