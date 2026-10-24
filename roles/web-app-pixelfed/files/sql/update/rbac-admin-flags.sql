UPDATE users
SET is_admin = IF(
    JSON_CONTAINS(%(admin_usernames)s, JSON_QUOTE(LOWER(username)))
    OR JSON_CONTAINS(%(admin_emails)s, JSON_QUOTE(LOWER(email)))
    OR id IN (
        SELECT user_id FROM user_oidc_mappings
        WHERE JSON_CONTAINS(%(admin_usernames)s, JSON_QUOTE(LOWER(oidc_id)))
    ),
    1,
    0
)
WHERE username <> %(kept_username)s;
SELECT ROW_COUNT();
