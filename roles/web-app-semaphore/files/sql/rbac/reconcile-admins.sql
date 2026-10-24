WITH member AS (
  SELECT lower(entry->>'username') AS username,
         lower(entry->>'email') AS email
  FROM jsonb_array_elements(%(members)s::jsonb) AS entry
),
kept AS (
  SELECT lower(login) AS username
  FROM jsonb_array_elements_text(%(kept)s::jsonb) AS login
),
desired AS (
  SELECT account.id,
         lower(account.username) IN (SELECT username FROM kept) AS kept,
         EXISTS (
           SELECT 1
           FROM member
           WHERE member.username = lower(account.username)
              OR (member.email <> '' AND member.email = lower(account.email))
         ) AS admin
  FROM public."user" AS account
)
UPDATE public."user" AS account
SET admin = desired.admin
FROM desired
WHERE account.id = desired.id
  AND account.admin IS DISTINCT FROM desired.admin
  AND (desired.admin OR NOT desired.kept)
RETURNING account.username, account.admin;
