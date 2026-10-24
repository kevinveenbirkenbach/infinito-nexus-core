# Semaphore UI

## Description

[Semaphore UI](https://semaphoreui.com/) is a modern web UI and API for running Ansible playbooks, Terraform/OpenTofu plans, and shell scripts on a schedule or on demand. This role deploys the official [`semaphoreui/semaphore`](https://github.com/semaphoreui/semaphore) container behind the Infinito.Nexus reverse proxy with central PostgreSQL, native Keycloak OIDC Single Sign-On, and optional LDAP login.

## Overview

The role deploys the single Semaphore container (with its embedded task runner) and wires it into the platform via `SEMAPHORE_*` environment variables. The setup wizard is bypassed by seeding the initial admin from rendered secrets, so a fresh deploy lands directly on the Semaphore login page. When SSO is enabled, the Keycloak `administrator` is created at deploy time as an external Semaphore admin via `semaphore user add --admin --external`; the OIDC callback matches it by email and signs the operator in as a Semaphore admin.

## Features

- **Central PostgreSQL:**
  `SEMAPHORE_DB_DIALECT=postgres` against the shared `svc-db-postgres` (or a per-role engine when not shared), with centralised backup and monitoring.

- **Native OIDC SSO:**
  Semaphore renders its own "Sign in with Keycloak" button via `SEMAPHORE_OIDC_PROVIDERS`; the Keycloak client is auto-provisioned by `web-app-keycloak`.

- **LDAP login:**
  When `svc-db-openldap` is present, Semaphore's login form binds against the central OpenLDAP directory (`SEMAPHORE_LDAP_*`). With LDAP enabled the form is LDAP-only; there is no local-password fallback.

- **LDAP role gate:**
  The LDAP search filter only finds members of the `administrator` and `user` role groups (`memberOf` under the roles OU), so a directory account without either group cannot sign in through the form.

- **OIDC role gate:**
  The provider's `email_claim` is a Go template rendered from `templates/oidc/email_claim.j2`. It yields the email only when the groups claim holds the `administrator` or `user` role group, so Semaphore refuses the Keycloak sign-in of every other realm account with a missing email claim and returns it to the login page.

- **Admin flag reconcile:**
  Every deploy with SSO or LDAP pre-provisions the members of the `administrator` role group as external Semaphore admins and converges the admin flag of every account to that group in PostgreSQL. The break-glass account and the platform administrator are never demoted.

- **Directory profile reconcile:**
  The same deploy writes the directory email, and the full name when the member list carries one, into every external account of an `administrator` or `user` member (`files/sql/rbac/converge-profiles.sql`). An email another account already holds is left in place.

- **Outsider sign-out:**
  The same deploy expires the sessions and API tokens of every external account that belongs to neither role group (`files/sql/rbac/expire-outsiders.sql`). The break-glass account and the platform administrator are exempt.

- **Break-glass local admin:**
  `SEMAPHORE_ADMIN*` seeds a local admin from the `web-app-semaphore-breakglass` user in every variant, reachable through the login form only when LDAP is disabled.

- **Embedded runner:**
  Automation executes inside the main container.

## Further Resources

- [Semaphore UI Official Website](https://semaphoreui.com/)
- [Semaphore Documentation](https://docs.semaphoreui.com/)
- [OIDC / Keycloak configuration](https://docs.semaphoreui.com/administration-guide/openid/keycloak/)
- [Semaphore GitHub Repository](https://github.com/semaphoreui/semaphore)
- [Corporate design review: before/after screenshots in light, dark, desktop and mobile](https://claude.ai/artifact/7gHWVy5u3jmoA9qni7W5Zi)
- [Corporate design review: screenshots in light, dark, desktop and mobile](https://claude.ai/artifact/4aT9GCukcd6kTnWzqTwwc4)
