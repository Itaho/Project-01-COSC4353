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
    signature_path VARCHAR(512) DEFAULT NULL, -- Signature image path
    cougar_id VARCHAR(20) DEFAULT NULL, -- Cougar ID (user-provided after login)
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
    reporter_cougar_id VARCHAR(20), -- cougarid
    category_id INT NOT NULL,  -- Type of report (from category)
    description TEXT NOT NULL,  -- Details of the incident
    status ENUM('submitted', 'under_review', 'approved_by_moderator', 'dismissed_by_moderator', 'resolved', 'dismissed') DEFAULT 'submitted',
    moderator_comments TEXT, 
    admin_comments TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    resolved_by INT,  -- Admin who resolved the report
    FOREIGN KEY (reporter_id) REFERENCES users(user_id),
    FOREIGN KEY (reported_user_id) REFERENCES users(user_id),
    FOREIGN KEY (category_id) REFERENCES report_categories(category_id),
    FOREIGN KEY (resolved_by) REFERENCES users(user_id)
);

CREATE TABLE organizational_units (
    unit_id INT AUTO_INCREMENT PRIMARY KEY,
    parent_id INT NULL,
    unit_name VARCHAR(255) NOT NULL,
    unit_code VARCHAR(255) NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (parent_id) REFERENCES organizational_units(unit_id) ON DELETE CASCADE
);

CREATE TABLE user_organizational_units ( -- Junction table that connects users to their OU
    user_ou_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    unit_id INT NOT NULL,
    role_in_unit VARCHAR(100) NOT NULL, -- e.g., 'student', 'faculty', 'staff', 'chair'
    is_primary BOOLEAN DEFAULT FALSE, -- Marks user's primary OU
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (unit_id) REFERENCES organizational_units(unit_id) ON DELETE CASCADE,
    UNIQUE KEY (user_id, unit_id, role_in_unit) -- Prevent duplicate assignments
);

CREATE TABLE approvers (
    approver_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    unit_id INT NULL, -- NULL means organizational-level approver 
    is_primary BOOLEAN DEFAULT FALSE,
    can_delegate BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (unit_id) REFERENCES organizational_units(unit_id) ON DELETE CASCADE
);

CREATE TABLE delegates (
    delegation_id INT AUTO_INCREMENT PRIMARY KEY,
    parent_approver_id INT NOT NULL, -- "Allow approvers to “delegate” the approval to another user"
    delegate_user_id INT NOT NULL,
    unit_id INT NOT NULL, -- Scope of delegation, NULL means organizational-level approver 
    start_date TIMESTAMP NOT NULL,
    end_date TIMESTAMP NOT NULL,
    status ENUM('active', 'expired', 'revoked') DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (parent_approver_id) REFERENCES approvers(approver_id) ON DELETE CASCADE,
    FOREIGN KEY (delegate_user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (unit_id) REFERENCES organizational_units(unit_id) ON DELETE CASCADE
);

CREATE TABLE workflows (
    workflow_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    request_type VARCHAR(50) NOT NULL,  -- e.g., 'petition', 'withdrawal'
    unit_id INT NULL,  -- NULL for organization-wide workflows
    is_active BOOLEAN DEFAULT TRUE,
    version DECIMAL DEFAULT 1.00, 
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (unit_id) REFERENCES organizational_units(unit_id) ON DELETE CASCADE
);

CREATE TABLE workflow_steps (
    step_id INT AUTO_INCREMENT PRIMARY KEY,
    workflow_id INT NOT NULL,
    step_order INT NOT NULL,  -- Determines sequence

    -- I did it this way so that you can choose whether to assign to an OU, a group like "admins", or a specific user. 
    -- Only one of these three is necessary, not all 3.
    approval_type ENUM('unit', 'role', 'user') NOT NULL,
    unit_id INT NULL,  -- Required if approval_type='unit'
    role_id INT NULL,  -- Required if approval_type='role'
    user_id INT NULL,  -- Required if approval_type='user'
    
    is_required BOOLEAN DEFAULT TRUE,
    min_approvals INT DEFAULT 1,  -- For multi-approver steps
    FOREIGN KEY (workflow_id) REFERENCES workflows(workflow_id) ON DELETE CASCADE,
    FOREIGN KEY (unit_id) REFERENCES organizational_units(unit_id) ON DELETE SET NULL,
    FOREIGN KEY (role_id) REFERENCES roles(role_id) ON DELETE SET NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL
);
