WITH member AS (
  SELECT lower(entry->>'username') AS username,
         lower(entry->>'email') AS email
  FROM jsonb_array_elements(%(members)s::jsonb) AS entry
),
kept AS (
  SELECT lower(login) AS username
  FROM jsonb_array_elements_text(%(kept)s::jsonb) AS login
),
outsider AS (
  SELECT account.id
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
SELECT user_id FROM expired_session
UNION ALL
SELECT user_id FROM expired_token;
