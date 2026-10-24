WITH member AS (
  SELECT lower(entry->>'email') AS email,
         entry->>'username' AS username,
         (entry->>'role')::integer AS role
  FROM jsonb_array_elements(%(members)s::jsonb) AS entry
),
desired AS (
  SELECT account.id,
         COALESCE(
           (
             SELECT min(member.role)
             FROM member
             WHERE member.email = lower(account.email)
                OR member.username = account.username
           ),
           %(user_role)s
         ) AS role
  FROM public."user" AS account
  WHERE account."pluginAuth" = %(plugin)s
)
UPDATE public."user" AS account
SET role = desired.role
FROM desired
WHERE account.id = desired.id
  AND account.role IS DISTINCT FROM desired.role
RETURNING account.username, account.role;
