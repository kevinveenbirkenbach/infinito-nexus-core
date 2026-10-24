<?php

declare(strict_types=1);

namespace Heptacom\AdminOpenAuth\Contract {
    final class RoleAssignment
    {
        public bool $isAdministrator = false;

        public array $roleIds = [];
    }

    final class User
    {
        public function __construct(private ?object $roleAssignment)
        {
        }

        public function getExtensionOfType(string $name, string $type): ?object
        {
            return $name === 'roleAssignment' && $this->roleAssignment instanceof $type ? $this->roleAssignment : null;
        }
    }
}

namespace Heptacom\AdminOpenAuth\Http\Route\Support {
    use Heptacom\AdminOpenAuth\Contract\User;

    final class UserRedirectReceivedEvent
    {
        public function __construct(public readonly User $user)
        {
        }
    }
}

namespace Symfony\Component\HttpKernel\Exception {
    class AccessDeniedHttpException extends \RuntimeException
    {
    }
}

namespace {

    use App\InfinitoRbac\AdminOpenAuthRoleGate;
    use Heptacom\AdminOpenAuth\Contract\RoleAssignment;
    use Heptacom\AdminOpenAuth\Contract\User;
    use Heptacom\AdminOpenAuth\Http\Route\Support\UserRedirectReceivedEvent;
    use PHPUnit\Framework\TestCase;
    use Symfony\Component\HttpKernel\Exception\AccessDeniedHttpException;

    require_once dirname(__DIR__, 7) . '/roles/web-app-shopware/files/php/oidc/role_gate.php';

    final class RoleGateTest extends TestCase
    {
        private static function event(?RoleAssignment $assignment): UserRedirectReceivedEvent
        {
            return new UserRedirectReceivedEvent(new User($assignment));
        }

        private static function assignment(bool $isAdministrator, array $roleIds): RoleAssignment
        {
            $assignment = new RoleAssignment();
            $assignment->isAdministrator = $isAdministrator;
            $assignment->roleIds = $roleIds;

            return $assignment;
        }

        public function testTheAdministratorRuleAdmitsTheSignIn(): void
        {
            (new AdminOpenAuthRoleGate())(self::event(self::assignment(true, [])));

            $this->addToAssertionCount(1);
        }

        public function testAnAclRoleAdmitsTheSignIn(): void
        {
            (new AdminOpenAuthRoleGate())(self::event(self::assignment(false, ['0190f4c5a6a07a1f8d0c3b1e2f3a4b5c'])));

            $this->addToAssertionCount(1);
        }

        public function testASignInWithoutAnyGrantIsRefused(): void
        {
            $this->expectException(AccessDeniedHttpException::class);

            (new AdminOpenAuthRoleGate())(self::event(self::assignment(false, [])));
        }

        public function testASignInWithoutARoleAssignmentIsRefused(): void
        {
            $this->expectException(AccessDeniedHttpException::class);

            (new AdminOpenAuthRoleGate())(self::event(null));
        }
    }
}
