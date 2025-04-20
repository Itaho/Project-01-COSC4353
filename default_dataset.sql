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
