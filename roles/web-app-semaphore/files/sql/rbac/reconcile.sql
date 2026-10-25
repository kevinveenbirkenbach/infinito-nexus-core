\getenv members RBAC_MEMBERS
\getenv kept SEMAPHORE_RBAC_KEPT
WITH administrator AS (
  SELECT lower(entry->>'username') AS username,
         lower(entry->>'email') AS email
  FROM jsonb_array_elements(:'members'::jsonb->'administrator') AS entry
),
kept AS (
  SELECT lower(login) AS username
  FROM jsonb_array_elements_text(:'kept'::jsonb) AS login
),
desired AS (
  SELECT account.id,
         lower(account.username) IN (SELECT username FROM kept) AS kept,
         EXISTS (
           SELECT 1
           FROM administrator
           WHERE administrator.username = lower(account.username)
              OR (administrator.email <> '' AND administrator.email = lower(account.email))
         ) AS admin
  FROM public."user" AS account
)
UPDATE public."user" AS account
SET admin = desired.admin
FROM desired
WHERE account.id = desired.id
  AND account.admin IS DISTINCT FROM desired.admin
  AND (desired.admin OR NOT desired.kept)
RETURNING 'CHANGED ' || account.username || ' admin=' || account.admin;
\set admin_changes :ROW_COUNT

WITH member AS (
  SELECT DISTINCT ON (lower(entry->>'username'))
         lower(entry->>'username') AS username,
         NULLIF(entry->>'email', '') AS email,
         NULLIF(entry->>'name', '') AS name
  FROM jsonb_each(:'members'::jsonb) AS grp
  CROSS JOIN jsonb_array_elements(grp.value) AS entry
  ORDER BY lower(entry->>'username')
),
desired AS (
  SELECT account.id,
         CASE
           WHEN member.email IS NULL THEN account.email
           WHEN EXISTS (
             SELECT 1
             FROM public."user" AS other
             WHERE other.id <> account.id
               AND lower(other.email) = lower(member.email)
           ) THEN account.email
           ELSE member.email
         END AS email,
         COALESCE(member.name, account.name) AS name
  FROM public."user" AS account
  JOIN member ON member.username = lower(account.username)
  WHERE account.external
)
UPDATE public."user" AS account
SET email = desired.email,
    name = desired.name
FROM desired
WHERE account.id = desired.id
  AND (account.email IS DISTINCT FROM desired.email OR account.name IS DISTINCT FROM desired.name)
RETURNING 'CHANGED ' || account.username || ' profile';
\set profile_changes :ROW_COUNT

WITH member AS (
  SELECT lower(entry->>'username') AS username,
         lower(entry->>'email') AS email
  FROM jsonb_each(:'members'::jsonb) AS grp
  CROSS JOIN jsonb_array_elements(grp.value) AS entry
),
kept AS (
  SELECT lower(login) AS username
  FROM jsonb_array_elements_text(:'kept'::jsonb) AS login
),
outsider AS (
  SELECT account.id, account.username
  FROM public."user" AS account
  WHERE account.external
    AND lower(account.username) NOT IN (SELECT username FROM kept)
    AND NOT EXISTS (
      SELECT 1
      FROM member
      WHERE member.username = lower(account.username)
         OR (member.email <> '' AND member.email = lower(account.email))
    )
),
expired_session AS (
  UPDATE public.session AS login_session
  SET expired = TRUE
  FROM outsider
  WHERE login_session.user_id = outsider.id
    AND NOT login_session.expired
  RETURNING login_session.user_id
),
expired_token AS (
  UPDATE public.user__token AS api_token
  SET expired = TRUE
  FROM outsider
  WHERE api_token.user_id = outsider.id
    AND NOT api_token.expired
  RETURNING api_token.user_id
)
SELECT 'CHANGED ' || outsider.username || ' signed out'
FROM outsider
WHERE outsider.id IN (SELECT user_id FROM expired_session UNION SELECT user_id FROM expired_token)
ORDER BY outsider.username;
\set expired_changes :ROW_COUNT

SELECT 'UNCHANGED' WHERE :admin_changes + :profile_changes + :expired_changes = 0;
