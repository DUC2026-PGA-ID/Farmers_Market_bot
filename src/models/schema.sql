-- =============================================
-- Database: agri_trade_db
-- Project: Immortal Digital - Farmers Market Bot
-- File: src/models/schema.sql
-- Description: Full database schema creation script
-- =============================================

CREATE DATABASE IF NOT EXISTS agri_trade_db;
USE agri_trade_db;

-- 1. Users Table
CREATE TABLE IF NOT EXISTS users (
    user_id INT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(50),
    full_name VARCHAR(100) NOT NULL,
    phone_number VARCHAR(20) UNIQUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 2. Crops Table
CREATE TABLE IF NOT EXISTS crops (
    crop_id INT PRIMARY KEY AUTO_INCREMENT,
    crop_name VARCHAR(100) NOT NULL,
    category VARCHAR(50) NOT NULL,
    unit VARCHAR(20) NOT NULL
);

-- 3. Markets Table
CREATE TABLE IF NOT EXISTS markets (
    market_id INT PRIMARY KEY AUTO_INCREMENT,
    market_name VARCHAR(100) NOT NULL,
    province VARCHAR(50) NOT NULL,
    district VARCHAR(50) NOT NULL,
    latitude DECIMAL(10,6),
    longitude DECIMAL(10,6)
);

-- 4. Buyers Table
CREATE TABLE IF NOT EXISTS buyers (
    buyer_id INT PRIMARY KEY AUTO_INCREMENT,
    company_name VARCHAR(100) NOT NULL,
    contact_person VARCHAR(100) NOT NULL,
    phone VARCHAR(20) UNIQUE NOT NULL,
    location VARCHAR(100) NOT NULL
);

-- 5. Alerts Table
CREATE TABLE IF NOT EXISTS alerts (
    alert_id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    crop_id INT NOT NULL,
    target_price DECIMAL(10,2) NOT NULL,
    alert_type ENUM('below','above') NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    -- Foreign Keys
    FOREIGN KEY (user_id) REFERENCES users(user_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (crop_id) REFERENCES crops(crop_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

-- 6. Price Records Table
CREATE TABLE IF NOT EXISTS price_records (
    price_id INT PRIMARY KEY AUTO_INCREMENT,
    crop_id INT NOT NULL,
    market_id INT NOT NULL,
    price_per_unit DECIMAL(10,2) NOT NULL,
    record_date DATE NOT NULL,
    source VARCHAR(100),
    -- Foreign Keys
    FOREIGN KEY (crop_id) REFERENCES crops(crop_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    FOREIGN KEY (market_id) REFERENCES markets(market_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

-- 7. Weather Logs Table
CREATE TABLE IF NOT EXISTS weather_logs (
    weather_id INT PRIMARY KEY AUTO_INCREMENT,
    market_id INT NOT NULL,
    forecast_date DATE NOT NULL,
    `condition` VARCHAR(50) NOT NULL,
    warning_level ENUM('none','low','medium','high') NOT NULL,
    -- Foreign Key
    FOREIGN KEY (market_id) REFERENCES markets(market_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

-- 8. Transactions Table
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id INT PRIMARY KEY AUTO_INCREMENT,
    buyer_id INT NOT NULL,
    -- Foreign Key
    FOREIGN KEY (buyer_id) REFERENCES buyers(buyer_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

-- =============================================
-- Indexes for performance
-- =============================================
CREATE INDEX idx_alerts_user ON alerts(user_id);
CREATE INDEX idx_price_crop_market ON price_records(crop_id, market_id);
CREATE INDEX idx_weather_market ON weather_logs(market_id, forecast_date);

-- =============================================
-- Sample Data (for testing commands)
-- =============================================
INSERT INTO crops (crop_name, category, unit) VALUES
('Rice', 'Grain', '50kg Sack'),
('Corn', 'Grain', 'kg'),
('Mango', 'Fruit', 'kg'),
('Cucumber', 'Vegetable', 'kg'),
('Damaged Rice', 'B-Grade Retail', 'Sack');

INSERT INTO markets (market_name, province, district, latitude, longitude) VALUES
('Kampot Central Market', 'Kampot', 'Kampot City', 10.6104, 104.1773),
('Battambang Main Market', 'Battambang', 'Battambang City', 13.0983, 103.2014);

INSERT INTO buyers (company_name, contact_person, phone, location) VALUES
('Green Trade Co.', 'Mr. Dara', '012345678', 'Kampot'),
('Fresh Farm Ltd.', 'Ms. Srey', '098765432', 'Battambang');
