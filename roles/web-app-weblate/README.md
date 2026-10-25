# Weblate

## Description

[Weblate](https://weblate.org) is a web-based continuous localization platform. It keeps a translation memory, glossaries and a review workflow, so a human translation can be written once, approved, and reused everywhere.

## Overview

In this deployment Weblate is the memory behind the translation gateway. [`web-svc-translate`](../web-svc-translate/) asks Weblate first: a string with an approved translation is returned verbatim and no engine is called. Translators reach Weblate's own UI at `web.translate.{{ DOMAIN_PRIMARY }}`, through Keycloak when SSO is deployed.

## Features

- **Translation memory:** every approved string is reusable by the gateway and by other components.
- **Glossaries:** terms that must survive a translation; the gateway rejects a machine answer that drops one.
- **Review workflow:** a translation becomes authoritative when a reviewer approves it.
- **API access:** the deploy reads the API token Weblate issued for its administrator and persists it in the token store, where the gateway reads it.
- **Role groups:** members of the `administrator` role group are superusers, members of `reviewer` join the built-in Reviewers team and members of `manager` the built-in Managers team; every other account loses the flag and both teams. [files/python/rbac_reconcile.py](./files/python/rbac_reconcile.py) runs as an RBAC hook of [sys-ctl-mtn-rbac-sync](../sys-ctl-mtn-rbac-sync/) at every deploy and on its timer; the platform administrator, bots and the anonymous account are never changed, and an account the OIDC sign-in creates is converged on the next run.

## Administration

The container's entrypoint provisions the administrator as the Weblate user `admin`; `WEBLATE_ADMIN_NAME` is its display name only. The role reads that account's API token out of Weblate's own database after the deploy and writes it to `sys-token-store` under `administrator` / `web-app-weblate`.

## Further resources

- [Weblate documentation](https://docs.weblate.org/)
- [The translation gateway that reads this memory](../web-svc-translate/)
