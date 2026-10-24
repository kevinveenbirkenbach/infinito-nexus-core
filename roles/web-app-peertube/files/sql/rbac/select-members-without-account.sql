SELECT member->>'username', member->>'email', member->>'role'
FROM jsonb_array_elements(%(members)s::jsonb) AS member
WHERE NOT EXISTS (
  SELECT 1
  FROM public."user" AS account
  WHERE lower(account.email) = lower(member->>'email')
     OR account.username = member->>'username'
);
