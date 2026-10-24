WITH member AS (
  SELECT DISTINCT ON (lower(entry->>'username'))
         lower(entry->>'username') AS username,
         NULLIF(entry->>'email', '') AS email,
         NULLIF(entry->>'name', '') AS name
  FROM jsonb_array_elements(%(members)s::jsonb) AS entry
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
RETURNING account.username;
