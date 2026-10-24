<?php
/**
 * Converge Snipe-IT accounts to the RBAC role groups of the deployment.
 *
 * Env (from the container):
 *   SNIPE_IT_RBAC_ADMINISTRATORS    JSON list of {username, email} holding the administrator role
 *   SNIPE_IT_RBAC_USERS             JSON list of {username, email} holding the user role
 *   SNIPE_IT_RBAC_PROTECTED         JSON list of usernames this script never changes
 *   SNIPE_IT_RBAC_USER_GROUP        name of the permission group every member joins
 *   SNIPE_IT_RBAC_USER_PERMISSIONS  JSON object of the permissions that group grants
 *
 * Exit: 0 with [CHANGED] or [UNCHANGED] on the last stdout line, 1 with [FAIL] on stderr.
 */
function fail(string $message): void
{
    fwrite(STDERR, "[FAIL] $message\n");
    exit(1);
}

function required_json(string $name): array
{
    $value = json_decode((string) getenv($name), true);
    if (!is_array($value)) {
        fail("$name is not a JSON list or object");
    }
    return $value;
}

$administrators = array_column(required_json('SNIPE_IT_RBAC_ADMINISTRATORS'), null, 'username');
$users = array_column(required_json('SNIPE_IT_RBAC_USERS'), null, 'username');
$protected = required_json('SNIPE_IT_RBAC_PROTECTED');
$groupName = (string) getenv('SNIPE_IT_RBAC_USER_GROUP');
if ($groupName === '') {
    fail('SNIPE_IT_RBAC_USER_GROUP is empty');
}
$groupPermissions = json_encode((object) required_json('SNIPE_IT_RBAC_USER_PERMISSIONS'));
$members = $administrators + $users;

try {
    require 'vendor/autoload.php';
    $app = require 'bootstrap/app.php';
    $app->make(Illuminate\Contracts\Console\Kernel::class)->bootstrap();

    $changed = false;

    $group = \App\Models\Group::where('name', $groupName)->first();
    if (!$group) {
        $group = new \App\Models\Group();
        $group->name = $groupName;
    }
    $group->permissions = $groupPermissions;
    if ($group->isDirty()) {
        if (!$group->save()) {
            fail("permission group '$groupName' was rejected: " . $group->getErrors());
        }
        echo "[GROUP] $groupName\n";
        $changed = true;
    }

    $settings = \App\Models\Setting::getSettings();
    if ((string) $settings->ldap_default_group !== (string) $group->id) {
        $settings->ldap_default_group = $group->id;
        $settings->save();
        echo "[DEFAULT GROUP] $groupName\n";
        $changed = true;
    }

    foreach ($members as $username => $member) {
        if (in_array($username, $protected, true)) {
            continue;
        }
        if (\App\Models\User::where('username', $username)->whereNull('deleted_at')->exists()) {
            continue;
        }
        $user = new \App\Models\User();
        $user->username = $username;
        $user->first_name = $username;
        $user->email = $member['email'];
        $user->activated = 1;
        $user->password = $user->noPassword();
        if (!$user->save()) {
            fail("account '$username' was rejected: " . $user->getErrors());
        }
        echo "[CREATED] $username\n";
        $changed = true;
    }

    foreach (\App\Models\User::whereNull('deleted_at')->get() as $user) {
        if (in_array($user->username, $protected, true)) {
            continue;
        }

        $decoded = json_decode((string) $user->permissions, true);
        $before = is_array($decoded) ? $decoded : [];
        $isAdministrator = isset($administrators[$user->username]);
        $permissions = $before;
        if ($isAdministrator) {
            $permissions['superuser'] = '1';
        } else {
            unset($permissions['superuser'], $permissions['admin']);
        }
        if ($permissions !== $before) {
            $user->permissions = json_encode((object) $permissions);
            $user->saveQuietly();
            echo ($isAdministrator ? '[PROMOTED] ' : '[DEMOTED] ') . $user->username . "\n";
            $changed = true;
        }

        $inGroup = $user->groups()->where('group_id', $group->id)->exists();
        if (isset($members[$user->username]) && !$inGroup) {
            $user->groups()->attach($group->id);
            echo "[JOINED] {$user->username}\n";
            $changed = true;
        } elseif (!isset($members[$user->username]) && $inGroup) {
            $user->groups()->detach($group->id);
            echo "[LEFT] {$user->username}\n";
            $changed = true;
        }
    }

    echo $changed ? "[CHANGED]\n" : "[UNCHANGED]\n";
} catch (Throwable $error) {
    fail($error->getMessage());
}
