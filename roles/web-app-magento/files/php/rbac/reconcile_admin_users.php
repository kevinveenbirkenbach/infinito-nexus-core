<?php
/**
 * Keep the Magento admin accounts of the administrator group active and deactivate every other
 * admin account, the protected accounts excepted.
 *
 * Every failure is caught and reduced to its message, so no database credential reaches stderr.
 *
 * Env, passed with `container exec -e <name>`:
 *   MAGENTO_RBAC_ROOT        Magento base directory, the one holding app/bootstrap.php
 *   MAGENTO_RBAC_ADMINS      JSON list of the usernames of the administrator group
 *   MAGENTO_RBAC_PROTECTED   JSON list of the usernames whose account stays untouched
 *
 * Exit: 0 with [CHANGED] or [UNCHANGED] on stdout, 1 with [FAIL] on stderr.
 */

declare(strict_types=1);

use Magento\Framework\App\Bootstrap;
use Magento\Framework\App\ResourceConnection;

function required(string $name): string
{
    $value = getenv($name);
    if ($value === false || $value === '') {
        fwrite(STDERR, "[FAIL] $name is empty\n");
        exit(1);
    }

    return $value;
}

function usernames(string $name): array
{
    $list = json_decode(required($name), true);
    if (!is_array($list)) {
        fwrite(STDERR, "[FAIL] $name is not a JSON list\n");
        exit(1);
    }

    return array_values(array_unique(array_map(static fn ($value): string => strtolower((string) $value), $list)));
}

$root = required('MAGENTO_RBAC_ROOT');
$admins = usernames('MAGENTO_RBAC_ADMINS');
$protected = usernames('MAGENTO_RBAC_PROTECTED');

if ($protected === []) {
    fwrite(STDERR, "[FAIL] MAGENTO_RBAC_PROTECTED must name the platform administrator\n");
    exit(1);
}

require_once $root . '/app/bootstrap.php';

$activate = [];
$deactivate = [];

try {
    $resource = Bootstrap::create(BP, $_SERVER)->getObjectManager()->get(ResourceConnection::class);
    $connection = $resource->getConnection();
    $table = $resource->getTableName('admin_user');

    foreach ($connection->fetchAll("SELECT user_id, username, is_active FROM {$table}") as $row) {
        $username = strtolower((string) $row['username']);
        if (in_array($username, $protected, true)) {
            continue;
        }

        $member = in_array($username, $admins, true);
        $active = (int) $row['is_active'] === 1;
        if ($member && !$active) {
            $activate[] = (int) $row['user_id'];
        } elseif (!$member && $active) {
            $deactivate[] = (int) $row['user_id'];
        }
    }

    if ($activate !== []) {
        $connection->update($table, ['is_active' => 1], ['user_id IN (?)' => $activate]);
    }
    if ($deactivate !== []) {
        $connection->update($table, ['is_active' => 0], ['user_id IN (?)' => $deactivate]);
    }
} catch (Throwable $error) {
    fwrite(STDERR, '[FAIL] ' . $error->getMessage() . "\n");
    exit(1);
}

if ($activate !== [] || $deactivate !== []) {
    printf("[CHANGED] %d admin account(s) activated and %d deactivated\n", count($activate), count($deactivate));
    exit(0);
}

echo "[UNCHANGED] the active admin accounts already follow the administrator group\n";
