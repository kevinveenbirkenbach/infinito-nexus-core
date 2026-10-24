<?php

/**
 * Refuse an AdminOpenAuth sign-in that no role-assignment rule granted anything.
 *
 * Registered in templates/adminopenauth.yaml.j2 as a listener of
 * UserRedirectReceivedEvent with a priority below the rule execution of
 * AdminOpenAuth, so it reads the RoleAssignment the rules produced before the
 * Shopware user is created or updated.
 */

declare(strict_types=1);

namespace App\InfinitoRbac;

use Heptacom\AdminOpenAuth\Contract\RoleAssignment;
use Heptacom\AdminOpenAuth\Http\Route\Support\UserRedirectReceivedEvent;
use Symfony\Component\HttpKernel\Exception\AccessDeniedHttpException;

final class AdminOpenAuthRoleGate
{
    public function __invoke(UserRedirectReceivedEvent $event): void
    {
        $assignment = $event->user->getExtensionOfType('roleAssignment', RoleAssignment::class);

        if ($assignment instanceof RoleAssignment && ($assignment->isAdministrator || $assignment->roleIds !== [])) {
            return;
        }

        throw new AccessDeniedHttpException('This account holds no Shopware role group.');
    }
}
