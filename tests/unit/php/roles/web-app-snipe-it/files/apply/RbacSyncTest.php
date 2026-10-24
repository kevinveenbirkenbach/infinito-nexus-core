<?php

declare(strict_types=1);

use PHPUnit\Framework\TestCase;

final class RbacSyncTest extends TestCase
{
    private const GROUP = 'web-app-snipe-it-user';

    private const GROUP_ID = 7;

    private const PERMISSIONS = ['assets.view' => '1'];

    private const AUTOLOAD = <<<'PHP'
        <?php
        namespace Illuminate\Contracts\Console {
            interface Kernel
            {
            }
        }

        namespace {
            $GLOBALS['STUB'] = json_decode((string) file_get_contents(getenv('STUB_STATE')), true);
            register_shutdown_function(static function (): void {
                file_put_contents(getenv('STUB_STATE'), json_encode($GLOBALS['STUB']));
            });
        }

        namespace App\Models {
            final class Query
            {
                public function __construct(private string $model, private array $conditions)
                {
                }

                public function where(string $column, $value): self
                {
                    return new self($this->model, $this->conditions + [$column => $value]);
                }

                public function whereNull(string $column): self
                {
                    return new self($this->model, $this->conditions + [$column => null]);
                }

                private function rows(): array
                {
                    $model = $this->model;
                    return array_values(array_filter(
                        $GLOBALS['STUB'][$model::TABLE],
                        function (array $row): bool {
                            foreach ($this->conditions as $column => $value) {
                                $actual = array_key_exists($column, $row) ? $row[$column] : null;
                                if ($value === null ? $actual !== null : $actual != $value) {
                                    return false;
                                }
                            }
                            return true;
                        }
                    ));
                }

                public function exists(): bool
                {
                    return $this->rows() !== [];
                }

                public function first(): ?Model
                {
                    $model = $this->model;
                    $rows = $this->rows();
                    return $rows ? $model::hydrate($rows[0]) : null;
                }

                public function get(): array
                {
                    $model = $this->model;
                    return array_map(static fn (array $row): Model => $model::hydrate($row), $this->rows());
                }
            }

            abstract class Model
            {
                private array $attributes = [];

                private array $original = [];

                public static function where(string $column, $value): Query
                {
                    return (new Query(static::class, []))->where($column, $value);
                }

                public static function whereNull(string $column): Query
                {
                    return (new Query(static::class, []))->whereNull($column);
                }

                public static function hydrate(array $row): static
                {
                    $model = new static();
                    $model->attributes = $row;
                    $model->original = $row;
                    return $model;
                }

                public function __get(string $name)
                {
                    return $this->attributes[$name] ?? null;
                }

                public function __set(string $name, $value): void
                {
                    $this->attributes[$name] = $value;
                }

                public function isDirty(): bool
                {
                    return $this->attributes !== $this->original;
                }

                public function save(): bool
                {
                    $rows = &$GLOBALS['STUB'][static::TABLE];
                    if (!isset($this->attributes['id'])) {
                        $this->attributes['id'] = 1 + max(array_merge([0], array_column($rows, 'id')));
                    }
                    $rows = array_values(array_filter($rows, fn (array $row): bool => $row['id'] !== $this->attributes['id']));
                    $rows[] = $this->attributes;
                    $this->original = $this->attributes;
                    return true;
                }

                public function saveQuietly(): bool
                {
                    return $this->save();
                }

                public function getErrors(): string
                {
                    return '';
                }
            }

            final class Group extends Model
            {
                public const TABLE = 'groups';
            }

            final class Setting extends Model
            {
                public const TABLE = 'settings';

                public static function getSettings(): self
                {
                    return self::hydrate($GLOBALS['STUB'][self::TABLE][0]);
                }
            }

            final class Membership
            {
                public function __construct(private int $userId, private ?int $groupId)
                {
                }

                public function where(string $column, int $groupId): self
                {
                    return new self($this->userId, $groupId);
                }

                public function exists(): bool
                {
                    return in_array([$this->userId, $this->groupId], $GLOBALS['STUB']['users_groups'], true);
                }

                public function attach(int $groupId): void
                {
                    $GLOBALS['STUB']['users_groups'][] = [$this->userId, $groupId];
                }

                public function detach(int $groupId): void
                {
                    $GLOBALS['STUB']['users_groups'] = array_values(array_filter(
                        $GLOBALS['STUB']['users_groups'],
                        fn (array $pair): bool => $pair !== [$this->userId, $groupId]
                    ));
                }
            }

            final class User extends Model
            {
                public const TABLE = 'users';

                public function noPassword(): string
                {
                    return '*';
                }

                public function groups(): Membership
                {
                    return new Membership((int) $this->id, null);
                }
            }
        }
        PHP;

    private const APP = <<<'PHP'
        <?php
        return new class {
            public function make(string $abstract): object
            {
                return new class {
                    public function bootstrap(): void
                    {
                    }
                };
            }
        };
        PHP;

    private string $root;

    private string $state;

    protected function setUp(): void
    {
        $this->root = sys_get_temp_dir() . '/snipeitrbac' . bin2hex(random_bytes(6));
        mkdir($this->root . '/vendor', 0700, true);
        mkdir($this->root . '/bootstrap', 0700, true);
        file_put_contents($this->root . '/vendor/autoload.php', self::AUTOLOAD);
        file_put_contents($this->root . '/bootstrap/app.php', self::APP);
        $this->state = $this->root . '/state.json';
    }

    protected function tearDown(): void
    {
        foreach (['vendor/autoload.php', 'bootstrap/app.php', 'state.json'] as $file) {
            if (is_file($this->root . '/' . $file)) {
                unlink($this->root . '/' . $file);
            }
        }
        rmdir($this->root . '/vendor');
        rmdir($this->root . '/bootstrap');
        rmdir($this->root);
    }

    /**
     * Build one Snipe-IT account row.
     *
     * @param int $id user id
     * @param string $username Snipe-IT username
     * @param array<string, string> $permissions permissions the account holds
     * @return array<string, mixed>
     */
    private static function user(int $id, string $username, array $permissions): array
    {
        return [
            'id' => $id,
            'username' => $username,
            'email' => "$username@example.org",
            'permissions' => json_encode((object) $permissions),
            'deleted_at' => null,
        ];
    }

    /**
     * Build one entry of an rbac_members list.
     *
     * @param string $username directory login of the member
     * @return array{username: string, email: string}
     */
    private static function member(string $username): array
    {
        return ['username' => $username, 'email' => "$username@example.org"];
    }

    /**
     * Store the site the way an earlier deploy or an administrator left it.
     *
     * @param list<array<string, mixed>> $users accounts
     * @param list<array{0: int, 1: int}> $memberships pairs of user id and group id
     * @param bool $groupExists whether the permission group exists with its permissions
     */
    private function seed(array $users, array $memberships, bool $groupExists): void
    {
        $groups = $groupExists
            ? [['id' => self::GROUP_ID, 'name' => self::GROUP, 'permissions' => json_encode((object) self::PERMISSIONS)]]
            : [];
        file_put_contents($this->state, json_encode([
            'users' => $users,
            'groups' => $groups,
            'settings' => [['id' => 1, 'ldap_default_group' => $groupExists ? self::GROUP_ID : null]],
            'users_groups' => $memberships,
        ]));
    }

    /**
     * Run the script against the stubbed Snipe-IT.
     *
     * @param list<array{username: string, email: string}> $administrators members of the administrator role
     * @param list<array{username: string, email: string}> $users members of the user role
     * @param list<string> $protected usernames the script never changes
     * @param string $group name of the permission group
     * @return array{0: string, 1: string, 2: int, 3: array<string, mixed>} stdout, stderr, exit code and the stored site
     */
    private function runScript(array $administrators, array $users, array $protected, string $group): array
    {
        $script = dirname(__DIR__, 7) . '/roles/web-app-snipe-it/files/php/apply/rbac_sync.php';
        $process = proc_open(
            [PHP_BINARY, $script],
            [1 => ['pipe', 'w'], 2 => ['pipe', 'w']],
            $pipes,
            $this->root,
            [
                'STUB_STATE' => $this->state,
                'SNIPE_IT_RBAC_ADMINISTRATORS' => json_encode($administrators),
                'SNIPE_IT_RBAC_USERS' => json_encode($users),
                'SNIPE_IT_RBAC_PROTECTED' => json_encode($protected),
                'SNIPE_IT_RBAC_USER_GROUP' => $group,
                'SNIPE_IT_RBAC_USER_PERMISSIONS' => json_encode((object) self::PERMISSIONS),
                'PATH' => (string) getenv('PATH'),
            ]
        );
        $stdout = (string) stream_get_contents($pipes[1]);
        $stderr = (string) stream_get_contents($pipes[2]);
        fclose($pipes[1]);
        fclose($pipes[2]);
        $code = proc_close($process);

        return [$stdout, $stderr, $code, json_decode((string) file_get_contents($this->state), true)];
    }

    /**
     * @param array<string, mixed> $site the stored site
     * @param string $username the account to read
     * @return array<string, string> the permissions of that account
     */
    private static function permissionsOf(array $site, string $username): array
    {
        foreach ($site['users'] as $row) {
            if ($row['username'] === $username) {
                return (array) json_decode((string) $row['permissions'], true);
            }
        }
        throw new RuntimeException("no account $username");
    }

    public function testAMemberJoinsThePermissionGroupAndANonMemberLeavesIt(): void
    {
        $this->seed([self::user(2, 'biber', []), self::user(3, 'mapache', [])], [[3, self::GROUP_ID]], true);

        [$stdout, $stderr, $code, $site] = $this->runScript([], [self::member('biber')], [], self::GROUP);

        $this->assertSame(0, $code, $stderr);
        $this->assertSame([[2, self::GROUP_ID]], $site['users_groups']);
        $this->assertStringContainsString('[JOINED] biber', $stdout);
        $this->assertStringContainsString('[LEFT] mapache', $stdout);
        $this->assertStringEndsWith("[CHANGED]\n", $stdout);
    }

    public function testAnAdministratorMemberIsPromotedAndAnOutsiderLosesSuperuserAndAdmin(): void
    {
        $this->seed(
            [self::user(2, 'biber', []), self::user(3, 'mapache', ['superuser' => '1', 'admin' => '1', 'assets.view' => '1'])],
            [[2, self::GROUP_ID]],
            true
        );

        [$stdout, $stderr, $code, $site] = $this->runScript([self::member('biber')], [], [], self::GROUP);

        $this->assertSame(0, $code, $stderr);
        $this->assertSame(['superuser' => '1'], self::permissionsOf($site, 'biber'));
        $this->assertSame(['assets.view' => '1'], self::permissionsOf($site, 'mapache'));
        $this->assertStringContainsString('[PROMOTED] biber', $stdout);
        $this->assertStringContainsString('[DEMOTED] mapache', $stdout);
    }

    public function testAMemberWithoutAnAccountIsCreatedAndJoinsTheGroup(): void
    {
        $this->seed([], [], true);

        [$stdout, $stderr, $code, $site] = $this->runScript([], [self::member('newbie')], [], self::GROUP);

        $this->assertSame(0, $code, $stderr);
        $this->assertCount(1, $site['users']);
        $this->assertSame('newbie', $site['users'][0]['username']);
        $this->assertSame('newbie@example.org', $site['users'][0]['email']);
        $this->assertSame([[$site['users'][0]['id'], self::GROUP_ID]], $site['users_groups']);
        $this->assertStringContainsString('[CREATED] newbie', $stdout);
    }

    public function testAProtectedAccountKeepsItsRightsAndGroups(): void
    {
        $this->seed([self::user(1, 'administrator', ['superuser' => '1'])], [[1, self::GROUP_ID]], true);

        [$stdout, $stderr, $code, $site] = $this->runScript([], [], ['administrator'], self::GROUP);

        $this->assertSame(0, $code, $stderr);
        $this->assertSame(['superuser' => '1'], self::permissionsOf($site, 'administrator'));
        $this->assertSame([[1, self::GROUP_ID]], $site['users_groups']);
        $this->assertSame("[UNCHANGED]\n", $stdout);
    }

    public function testAMissingPermissionGroupIsCreatedAndBecomesTheLdapDefaultGroup(): void
    {
        $this->seed([], [], false);

        [$stdout, $stderr, $code, $site] = $this->runScript([], [], [], self::GROUP);

        $this->assertSame(0, $code, $stderr);
        $this->assertCount(1, $site['groups']);
        $this->assertSame(self::GROUP, $site['groups'][0]['name']);
        $this->assertSame(json_encode((object) self::PERMISSIONS), $site['groups'][0]['permissions']);
        $this->assertSame($site['groups'][0]['id'], $site['settings'][0]['ldap_default_group']);
        $this->assertStringContainsString('[GROUP] ' . self::GROUP, $stdout);
        $this->assertStringContainsString('[DEFAULT GROUP] ' . self::GROUP, $stdout);
    }

    public function testASecondRunReportsUnchanged(): void
    {
        $this->seed([self::user(2, 'biber', []), self::user(3, 'mapache', ['superuser' => '1'])], [[3, self::GROUP_ID]], false);
        $administrators = [self::member('biber')];
        $users = [self::member('newbie')];

        $this->runScript($administrators, $users, [], self::GROUP);
        [$stdout, $stderr, $code] = $this->runScript($administrators, $users, [], self::GROUP);

        $this->assertSame(0, $code, $stderr);
        $this->assertSame("[UNCHANGED]\n", $stdout);
    }

    public function testAnEmptyGroupNameFails(): void
    {
        $this->seed([], [], true);

        [, $stderr, $code] = $this->runScript([], [], [], '');

        $this->assertSame(1, $code);
        $this->assertStringContainsString('[FAIL] SNIPE_IT_RBAC_USER_GROUP is empty', $stderr);
    }
}
