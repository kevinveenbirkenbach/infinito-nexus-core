CREATE TEMP TABLE rbac_roles AS
SELECT r.name, ARRAY(SELECT json_array_elements_text(r.permissions)) AS permissions
FROM json_to_recordset(:'roles'::json) AS r(name text, permissions json);

INSERT INTO roles (type, name, permissions)
SELECT 'user', w.name, w.permissions
FROM rbac_roles w
WHERE NOT EXISTS (SELECT 1 FROM roles r WHERE r.name = w.name);

UPDATE roles r
SET permissions = w.permissions
FROM rbac_roles w
WHERE r.name = w.name
  AND r.type = 'user'
  AND r.permissions IS DISTINCT FROM w.permissions;

CREATE TEMP TABLE rbac_wanted AS
SELECT DISTINCT ON (lower(w.email))
       lower(w.username) AS username,
       lower(w.email) AS email,
       CASE WHEN w.role_name = :'admin_role'
            THEN :'admin_role_id'::int
            ELSE (SELECT r.id FROM roles r WHERE r.name = w.role_name AND r.type = 'user')
       END AS role_id
FROM json_to_recordset(:'wanted'::json) AS w(username text, email text, role_name text, rank int)
WHERE length(w.email) > 0
ORDER BY lower(w.email), w.rank;

UPDATE users u
SET user_role_id = w.role_id,
    status = 'enabled'
FROM rbac_wanted w
WHERE lower(u.email) = w.email
  AND u.type = 'user'
  AND (u.user_role_id IS DISTINCT FROM w.role_id OR u.status <> 'enabled');

INSERT INTO users (username, password_login, password, email, name, type, user_role_id, status)
SELECT w.username, false, NULL, w.email, w.username, 'user', w.role_id, 'enabled'
FROM rbac_wanted w
WHERE NOT EXISTS (
  SELECT 1 FROM users u WHERE lower(u.email) = w.email OR lower(u.username) = w.username
);

UPDATE users u
SET status = 'disabled'
WHERE u.type = 'user'
  AND u.status = 'enabled'
  AND lower(u.email) NOT IN (SELECT email FROM rbac_wanted)
  AND lower(u.username) NOT IN (SELECT lower(p) FROM json_array_elements_text(:'protected'::json) AS p);

SELECT CASE WHEN EXISTS (
         SELECT 1
         FROM rbac_wanted w
         LEFT JOIN users u ON lower(u.email) = w.email AND u.type = 'user'
         WHERE u.id IS NULL OR u.user_role_id IS DISTINCT FROM w.role_id OR u.status <> 'enabled'
       ) THEN '[FAIL] a Listmonk RBAC member is not converged'
       ELSE '[OK]'
       END AS converged;
