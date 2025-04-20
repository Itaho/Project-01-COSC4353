-- Destroy and recreate database from scratch
DROP DATABASE IF EXISTS moosefactory_sql;
CREATE DATABASE moosefactory_sql;

use moosefactory_sql;

-- Roles Table
CREATE TABLE roles (
    role_id INT AUTO_INCREMENT PRIMARY KEY,
    role_name VARCHAR(256) UNIQUE NOT NULL,
    description TEXT
);

-- Permissions Table
CREATE TABLE permissions (
    permission_id INT AUTO_INCREMENT PRIMARY KEY,
    permission_name VARCHAR(256) UNIQUE NOT NULL
);

-- Role-Permissions Junction Table
CREATE TABLE role_permissions (
    role_id INT,
    permission_id INT,
    PRIMARY KEY (role_id, permission_id),
    FOREIGN KEY (role_id) REFERENCES roles(role_id),
    FOREIGN KEY (permission_id) REFERENCES permissions(permission_id)
);

-- Users Table
CREATE TABLE users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(256) NOT NULL,
    email VARCHAR(256) UNIQUE NOT NULL,
    role_id INT DEFAULT 2, -- Default 'basicuser' (assume role_id=2)
    signature_path VARCHAR(512), -- New column for storing signature image path
    status ENUM('active', 'inactive') DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (role_id) REFERENCES roles(role_id)
);

CREATE TABLE applications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Add new tables here. I will implement on the front end. 

CREATE TABLE requests (
    request_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,  -- The user who submitted the request
    form_type VARCHAR(256) NOT NULL,  -- Type of form (e.g., academic request)
    status ENUM('draft', 'submitted', 'returned', 'approved', 'pending') DEFAULT 'draft',
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE approvals (
    approval_id INT AUTO_INCREMENT PRIMARY KEY,
    request_id INT NOT NULL,  -- The request being approved
    approver_id INT NOT NULL,  -- The user who is approving the request
    status ENUM('pending', 'approved', 'returned') DEFAULT 'pending',
    comments TEXT,  -- Comments from the approver (e.g., why it was returned)
    approved_at TIMESTAMP,  -- Timestamp when the request was approved
    FOREIGN KEY (request_id) REFERENCES requests(request_id),
    FOREIGN KEY (approver_id) REFERENCES users(user_id)
);

CREATE TABLE documents (
    document_id INT AUTO_INCREMENT PRIMARY KEY,
    request_id INT NOT NULL,  -- The request associated with this document
    document_path VARCHAR(512) NOT NULL,  -- Path to the generated PDF file
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (request_id) REFERENCES requests(request_id)
);

-- v.4 --

CREATE TABLE report_categories (
    category_id INT AUTO_INCREMENT PRIMARY KEY,
    category_name VARCHAR(256) NOT NULL,
    description TEXT,
    severity_level ENUM('low', 'medium', 'high', 'critical') DEFAULT 'medium',
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE reports (
    report_id INT AUTO_INCREMENT PRIMARY KEY,
    reporter_id INT NOT NULL,  -- User who is making the report
    reported_user_id INT NOT NULL,  -- User being reported
    category_id INT NOT NULL,  -- Type of report (from category)
    description TEXT NOT NULL,  -- Details of the incident
    status ENUM('submitted', 'under_review', 'resolved', 'dismissed') DEFAULT 'submitted',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    resolved_by INT,  -- Admin who resolved the report
    resolution_notes TEXT,
    FOREIGN KEY (reporter_id) REFERENCES users(user_id),
    FOREIGN KEY (reported_user_id) REFERENCES users(user_id),
    FOREIGN KEY (category_id) REFERENCES report_categories(category_id),
    FOREIGN KEY (resolved_by) REFERENCES users(user_id)
);
