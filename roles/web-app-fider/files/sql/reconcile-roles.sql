-- Args: members (JSON array of {username, email, role}), bootstrap_email (the administrator create-admin-user.sql converges), visitor_role.
-- Returns one row: the number of rows that changed.
WITH tenant AS (
    SELECT id FROM tenants ORDER BY id LIMIT 1
), member AS (
    SELECT DISTINCT ON (lower(entry->>'email'))
           lower(entry->>'email') AS email,
           entry->>'username' AS username,
           (entry->>'role')::integer AS role
    FROM jsonb_array_elements(%(members)s::jsonb) AS entry
    WHERE COALESCE(entry->>'email', '') <> ''
    ORDER BY lower(entry->>'email'), (entry->>'role')::integer DESC
), created AS (
    INSERT INTO users (name, email, created_at, tenant_id, role, status, avatar_type, avatar_bkey)
    SELECT member.username, member.email, NOW(), tenant.id, member.role, 1, 2, ''
    FROM member CROSS JOIN tenant
    WHERE member.email <> lower(%(bootstrap_email)s)
      AND NOT EXISTS (
          SELECT 1 FROM users
          WHERE users.tenant_id = tenant.id AND lower(users.email) = member.email
      )
    RETURNING 1
), desired AS (
    SELECT users.id,
           COALESCE(
               (SELECT member.role FROM member WHERE member.email = lower(users.email)),
               %(visitor_role)s
           ) AS role
    FROM users
    JOIN tenant ON tenant.id = users.tenant_id
    WHERE lower(users.email) <> lower(%(bootstrap_email)s)
), updated AS (
    UPDATE users
    SET role = desired.role
    FROM desired
    WHERE users.id = desired.id
      AND users.role IS DISTINCT FROM desired.role
    RETURNING 1
)
SELECT (SELECT COUNT(*) FROM created) + (SELECT COUNT(*) FROM updated);
