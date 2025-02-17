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