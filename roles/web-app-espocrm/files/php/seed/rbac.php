<?php
// nocheck: mirrored-unit-test - requires /var/www/html/bootstrap.php at the top level
// and writes roles, teams, users and config through EspoCRM's own container
/**
 * Reconcile the RBAC roles of the deployment with EspoCRM.
 *
 * Env (from the calling task):
 *   ESPOCRM_RBAC_TIERS      JSON {tier: {"path": groups claim value, "team": team name,
 *                           "role": role name, "access": "manage"|"use", "members": [username, ...]}}
 *   ESPOCRM_RBAC_ADMINS       JSON list of the usernames that hold the administrator role
 *   ESPOCRM_RBAC_ADMIN_GROUP  groups claim value of the administrator role
 *   ESPOCRM_RBAC_PROTECTED    JSON list of the usernames whose type and teams stay untouched
 *   ESPOCRM_RBAC_CLAIM      name of the groups claim
 *
 * Exit: 0 with [CHANGED] or [UNCHANGED] on stdout, 1 with [FAIL] on stderr.
 */

require "/var/www/html/bootstrap.php";

const READ_ONLY_SCOPES = ['User', 'Team'];

const PERMISSIONS = [
    'manage' => [
        'assignmentPermission' => 'all',
        'userPermission' => 'all',
        'messagePermission' => 'all',
        'portalPermission' => 'no',
        'groupEmailAccountPermission' => 'team',
        'exportPermission' => 'yes',
        'massUpdatePermission' => 'yes',
        'dataPrivacyPermission' => 'no',
        'followerManagementPermission' => 'all',
        'auditPermission' => 'yes',
        'mentionPermission' => 'all',
        'userCalendarPermission' => 'all',
    ],
    'use' => [
        'assignmentPermission' => 'team',
        'userPermission' => 'team',
        'messagePermission' => 'all',
        'portalPermission' => 'no',
        'groupEmailAccountPermission' => 'team',
        'exportPermission' => 'no',
        'massUpdatePermission' => 'no',
        'dataPrivacyPermission' => 'no',
        'followerManagementPermission' => 'no',
        'auditPermission' => 'no',
        'mentionPermission' => 'all',
        'userCalendarPermission' => 'team',
    ],
];

const LEVEL_PREFERENCES = [
    'manage' => ['read' => ['all'], 'edit' => ['all'], 'delete' => ['all'], 'stream' => ['all']],
    'use' => [
        'read' => ['team', 'own', 'no'],
        'edit' => ['own', 'team', 'no'],
        'delete' => ['no'],
        'stream' => ['team', 'own', 'no'],
    ],
];

function record_levels($acl): array
{
    if ($acl === true || $acl === 'record') {
        return ['all', 'team', 'own', 'no'];
    }

    return array_values(array_filter(
        ['all', 'team', 'own', 'no'],
        static fn (string $level): bool => str_contains(strtolower($acl), $level)
    ));
}

function record_permissions($acl, string $access): array
{
    $allowed = record_levels($acl);
    $permissions = ['create' => 'yes'];

    foreach (LEVEL_PREFERENCES[$access] as $action => $preferences) {
        $permissions[$action] = current(array_intersect($preferences, $allowed)) ?: 'no';
    }

    return $permissions;
}

function env_json(string $key): array
{
    $raw = getenv($key);

    if ($raw === false || $raw === '') {
        fwrite(STDERR, "[FAIL] {$key} is empty\n");
        exit(1);
    }

    $value = json_decode($raw, true, 512, JSON_THROW_ON_ERROR);

    if (!is_array($value)) {
        fwrite(STDERR, "[FAIL] {$key} is not a JSON list or object\n");
        exit(1);
    }

    return $value;
}

function role_data(array $scopes, string $access): array
{
    $data = [];

    foreach ($scopes as $scope => $definition) {
        $acl = $definition['acl'] ?? false;

        if ($acl === 'boolean') {
            $data[$scope] = true;
            continue;
        }

        if ($acl !== true && !(is_string($acl) && str_starts_with($acl, 'record'))) {
            continue;
        }

        $data[$scope] = in_array($scope, READ_ONLY_SCOPES, true)
            ? ['create' => 'no', 'read' => 'all', 'edit' => 'no', 'delete' => 'no']
            : record_permissions($acl, $access);
    }

    ksort($data);

    return $data;
}

function upsert_named(\Espo\ORM\EntityManager $entityManager, string $entityType, string $name, array $values): array
{
    $entity = $entityManager->getRDBRepository($entityType)->where(['name' => $name])->findOne()
        ?? $entityManager->getNewEntity($entityType);

    foreach (array_keys($values) as $key) {
        if (!$entity->isNew() && str_ends_with($key, 'Ids')) {
            $entity->loadLinkMultipleField(substr($key, 0, -3));
        }
    }

    $before = $entity->isNew() ? null : json_encode(array_map(fn ($key) => $entity->get($key), array_keys($values)));

    $entity->set('name', $name);
    $entity->set($values);

    $after = json_encode(array_map(fn ($key) => $entity->get($key), array_keys($values)));

    if ($before === $after) {
        return [$entity, false];
    }

    $entityManager->saveEntity($entity);

    return [$entity, true];
}

$tiers = env_json('ESPOCRM_RBAC_TIERS');
$admins = array_map('strtolower', env_json('ESPOCRM_RBAC_ADMINS'));
$protected = array_map('strtolower', env_json('ESPOCRM_RBAC_PROTECTED'));
$claim = getenv('ESPOCRM_RBAC_CLAIM');
$adminGroup = getenv('ESPOCRM_RBAC_ADMIN_GROUP');

if ($claim === false || $claim === '') {
    fwrite(STDERR, "[FAIL] ESPOCRM_RBAC_CLAIM is empty\n");
    exit(1);
}

if ($adminGroup === false || $adminGroup === '') {
    fwrite(STDERR, "[FAIL] ESPOCRM_RBAC_ADMIN_GROUP is empty\n");
    exit(1);
}

$app = new \Espo\Core\Application();
$app->setupSystemUser();

$container = $app->getContainer();
$entityManager = $container->getByClass(\Espo\Core\ORM\EntityManager::class);
$config = $container->get('config');
$writer = $container->get('injectableFactory')->create('\Espo\Core\Utils\Config\ConfigWriter');
$aclCacheClearer = $container->get('injectableFactory')->create('\Espo\Core\Acl\Cache\Clearer');
$scopes = $container->get('metadata')->get(['scopes']) ?? [];

$changed = false;
$teamIds = [];
$teamColumns = new \stdClass();
$wantedTeams = [];
$allowedGroups = [$adminGroup];

foreach ($tiers as $tier => $definition) {
    [$role, $roleChanged] = upsert_named($entityManager, 'Role', $definition['role'], PERMISSIONS[$definition['access']] + [
        'data' => (object) role_data($scopes, $definition['access']),
        'fieldData' => (object) [],
    ]);
    [$team, $teamChanged] = upsert_named($entityManager, 'Team', $definition['team'], [
        'rolesIds' => [$role->getId()],
    ]);
    $changed = $changed || $roleChanged || $teamChanged;

    $teamIds[] = $team->getId();
    $teamColumns->{$team->getId()} = (object) ['group' => $definition['path']];
    $allowedGroups[] = $definition['path'];

    foreach ($definition['members'] as $member) {
        $wantedTeams[strtolower($member)][] = $team->getId();
    }
}

$settings = [
    'aclStrictMode' => true,
    'oidcGroupClaim' => $claim,
    'oidcSyncTeams' => true,
    'oidcTeamsIds' => $teamIds,
    'oidcTeamsColumns' => $teamColumns,
    'infinitoOidcAllowedGroups' => $allowedGroups,
    'infinitoOidcAdministratorGroups' => [$adminGroup],
    'infinitoOidcProtectedUsers' => $protected,
];

$settingsChanged = false;

foreach ($settings as $key => $value) {
    if (json_encode($config->get($key)) !== json_encode($value)) {
        $writer->set($key, $value);
        $settingsChanged = true;
    }
}

if ($settingsChanged) {
    $writer->save();
    $changed = true;
}

$users = $entityManager->getRDBRepository('User')
    ->where(['type' => [\Espo\Entities\User::TYPE_ADMIN, \Espo\Entities\User::TYPE_REGULAR]])
    ->find();

foreach ($users as $user) {
    $userName = strtolower($user->getUserName());

    if (in_array($userName, $protected, true)) {
        continue;
    }

    $user->set('type', in_array($userName, $admins, true)
        ? \Espo\Entities\User::TYPE_ADMIN
        : \Espo\Entities\User::TYPE_REGULAR);

    $user->loadLinkMultipleField('teams');
    $current = $user->getLinkMultipleIdList('teams');
    $wanted = array_values(array_unique(array_merge(
        array_diff($current, $teamIds),
        $wantedTeams[$userName] ?? []
    )));
    sort($current);
    sort($wanted);

    if ($current !== $wanted) {
        $user->set('teamsIds', $wanted);
    }

    if ($user->isAttributeChanged('type') || $user->isAttributeChanged('teamsIds')) {
        $entityManager->saveEntity($user);
        $aclCacheClearer->clearForUser($user);
        $changed = true;
    }
}

echo $changed ? "[CHANGED] RBAC roles, teams and users reconciled\n" : "[UNCHANGED] RBAC roles, teams and users already match\n";
