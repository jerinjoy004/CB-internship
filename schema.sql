CREATE DATABASE IF NOT EXISTS finance_db;
USE finance_db;

-- Users Table
CREATE TABLE IF NOT EXISTS users (
    userID INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100),
    email VARCHAR(100) UNIQUE,
    password VARCHAR(255),
    status VARCHAR(10) DEFAULT 'active',
    date_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Categories Table
CREATE TABLE IF NOT EXISTS categories (
    categoryID INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100),
    type ENUM('credit', 'debit') NOT NULL,
    userID INT,
    FOREIGN KEY (userID) REFERENCES users(userID)
        ON DELETE SET NULL
        ON UPDATE CASCADE
);

-- Transactions Table
CREATE TABLE IF NOT EXISTS transactions (
    transactionID INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(100),
    amount DECIMAL(10,2),
    date DATE,
    notes TEXT,
    categoryID INT,
    userID INT,
    FOREIGN KEY (categoryID) REFERENCES categories(categoryID)
        ON DELETE SET NULL
        ON UPDATE CASCADE,
    FOREIGN KEY (userID) REFERENCES users(userID)
        ON DELETE CASCADE
        ON UPDATE CASCADE
);
