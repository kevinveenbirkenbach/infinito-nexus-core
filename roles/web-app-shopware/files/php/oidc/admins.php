<?php
// nocheck: mirrored-unit-test - rewrites the admin flag and the ACL role links straight
// through Shopware's database connection; top-level procedural code
/**
 * Withdraw the admin flag from every Keycloak-linked Shopware user that is
 * not a member of the administrator group, and the Editor ACL role from every
 * Keycloak-linked user that is not a member of the editor group.
 *
 * Required env:
 *   DATABASE_URL          connection string of the Shopware database
 *   KEEP_ADMINS           JSON list of usernames and emails that keep the admin flag
 *   KEEP_EDITORS          JSON list of usernames and emails that keep the Editor ACL role
 *   ACL_EDITOR_ROLE_NAME  name of the Editor ACL role
 *
 * Output: [CHANGED] or [UNCHANGED] with the number of rewritten rows.
 */

declare(strict_types=1);

function keep_list(string $key): array
{
    $keep = json_decode((string) getenv($key), true, 512, JSON_THROW_ON_ERROR);

    if (!is_array($keep) || $keep === []) {
        fwrite(STDERR, "{$key} must be a non-empty JSON list\n");
        exit(1);
    }

    return array_values(array_unique(array_map(static fn ($value): string => strtolower((string) $value), $keep)));
}

function withdraw(PDO $pdo, string $sql, array $keep, array $leading = []): int
{
    $placeholders = implode(', ', array_fill(0, count($keep), '?'));
    $statement = $pdo->prepare(str_replace('{keep}', $placeholders, $sql));
    $statement->execute([...$leading, ...$keep, ...$keep]);

    return $statement->rowCount();
}

$keepAdmins = keep_list('KEEP_ADMINS');
$keepEditors = keep_list('KEEP_EDITORS');
$editorRole = (string) getenv('ACL_EDITOR_ROLE_NAME');

if ($editorRole === '') {
    fwrite(STDERR, "ACL_EDITOR_ROLE_NAME must be set\n");
    exit(1);
}

$url = parse_url((string) getenv('DATABASE_URL'));

if (!is_array($url) || !isset($url['host'], $url['path'], $url['user'], $url['pass'])) {
    fwrite(STDERR, "DATABASE_URL must name a user, a password, a host and a database\n");
    exit(1);
}

$dsn = sprintf(
    'mysql:host=%s;port=%d;dbname=%s;charset=utf8mb4',
    $url['host'],
    $url['port'] ?? 3306,
    ltrim($url['path'], '/')
);

$pdo = new PDO($dsn, rawurldecode($url['user']), rawurldecode($url['pass']), [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);

$admins = withdraw(
    $pdo,
    'UPDATE `user` SET admin = 0 WHERE admin = 1'
    . ' AND id IN (SELECT user_id FROM `heptacom_admin_open_auth_user_key`)'
    . ' AND LOWER(username) NOT IN ({keep})'
    . ' AND LOWER(email) NOT IN ({keep})',
    $keepAdmins
);

$editors = withdraw(
    $pdo,
    'DELETE aur FROM `acl_user_role` aur'
    . ' JOIN `acl_role` ar ON ar.id = aur.acl_role_id'
    . ' JOIN `user` u ON u.id = aur.user_id'
    . ' WHERE ar.name = ?'
    . ' AND u.id IN (SELECT user_id FROM `heptacom_admin_open_auth_user_key`)'
    . ' AND LOWER(u.username) NOT IN ({keep})'
    . ' AND LOWER(u.email) NOT IN ({keep})',
    $keepEditors,
    [$editorRole]
);

printf(
    "%s admin flag withdrawn from %d row(s), Editor role withdrawn from %d row(s)\n",
    $admins + $editors > 0 ? '[CHANGED]' : '[UNCHANGED]',
    $admins,
    $editors
);
