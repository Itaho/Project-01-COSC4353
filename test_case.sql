-- Create a user
INSERT INTO users (name, email, role_id) 
VALUES ('John Doe', 'john@example.com', 1);

-- Deactivate a user
UPDATE users SET status = 'inactive' WHERE email = 'john@example.com';

-- Check permissions for a role
SELECT p.permission_name 
FROM role_permissions rp
JOIN permissions p ON rp.permission_id = p.permission_id
WHERE rp.role_id = 1;