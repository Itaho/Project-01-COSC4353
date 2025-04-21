-- Add default roles
INSERT INTO roles (role_name, description) VALUES
    ('admin', 'Full access to manage users and roles'),
    ('basicuser', 'Default role with limited access');

-- Add permissions (example)
INSERT INTO permissions (permission_name) VALUES
    ('create_user'),
    ('read_user'),
    ('update_user'),
    ('delete_user'),
    ('assign_role');

-- Assign permissions to 'admin' role
INSERT INTO role_permissions (role_id, permission_id)
VALUES
    (1, 1), (1, 2), (1, 3), (1, 4), (1, 5); -- Assign all permissions to admin
SHOW TABLES

INSERT INTO report_categories (category_name, description, severity_level) VALUES
('Harassment', 'Unwanted, persistent behavior causing distress', 'high'),
('Inappropriate Content', 'Sharing offensive or explicit material', 'medium'),
('Abusive Language', 'Use of offensive or threatening language', 'medium'),
('Policy Violation', 'Breach of community guidelines', 'medium'),
('Spam', 'Excessive unsolicited messages', 'low'),
('Other', 'Other type of report not listed', 'low');

INSERT INTO organizational_units (unit_name, unit_code, description)
VALUES ('University of Houston', 'UH', 'Main University Organization');

INSERT INTO organizational_units (parent_id, unit_name, unit_code, description)
VALUES 
(1, 'College of Engineering', 'ENGR', 'Engineering programs'),
(1, 'College of Business', 'BUSI', 'Business programs'),
(1, 'College of Natural Sciences and Mathematics', 'NSM', 'Science and Math programs');

INSERT INTO organizational_units (parent_id, unit_name, unit_code, description)
VALUES 
(2, 'Department of Computer Science', 'CS', 'Computer Science programs'),
(2, 'Department of Electrical Engineering', 'EE', 'Electrical Engineering programs'),
(2, 'Department of Mechanical Engineering', 'ME', 'Mechanical Engineering programs');

INSERT INTO organizational_units (parent_id, unit_name, unit_code, description)
VALUES 
(3, 'Department of Accounting', 'ACCT', 'Accounting programs'),
(3, 'Department of Marketing', 'MKTG', 'Marketing programs');

-- For v0.4
INSERT INTO permissions (permission_name) VALUES
    ('manage_workflows'),
    ('manage_approvers'),
    ('view_all_reports'),
    ('resolve_reports');

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.role_id, p.permission_id 
FROM roles r, permissions p
WHERE r.role_name = 'admin' 
AND p.permission_name IN ('manage_workflows', 'manage_approvers', 'view_all_reports', 'resolve_reports');
