CREATE TABLE IF NOT EXISTS news_articles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    source_name VARCHAR(255) NOT NULL,
    source_url VARCHAR(1024) NOT NULL,
    title VARCHAR(512) NOT NULL,
    content TEXT NOT NULL,
    summary TEXT,
    topic VARCHAR(128) NOT NULL,
    published_at DATETIME,
    scraped_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_topic (topic),
    INDEX idx_scraped_at (scraped_at)
);

CREATE TABLE IF NOT EXISTS generated_posts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    topic VARCHAR(128) NOT NULL,
    draft_content TEXT NOT NULL,
    final_content TEXT,
    article_ids JSON NOT NULL,
    analyzer_model VARCHAR(128) NOT NULL,
    reviewer_model VARCHAR(128),
    review_notes TEXT,
    review_status ENUM('pending', 'approved', 'revised', 'rejected') DEFAULT 'pending',
    threads_post_id VARCHAR(255),
    status ENUM('draft', 'reviewed', 'published', 'failed') DEFAULT 'draft',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    published_at DATETIME,
    INDEX idx_topic (topic),
    INDEX idx_status (status)
);
