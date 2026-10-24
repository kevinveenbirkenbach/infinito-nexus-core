UPDATE public."user"
SET "pluginAuth" = %(plugin)s
WHERE "pluginAuth" IS NULL
  AND username <> %(root_username)s
  AND lower(email) IN (
    SELECT lower(value) FROM jsonb_array_elements_text(%(emails)s::jsonb)
  )
RETURNING username;
