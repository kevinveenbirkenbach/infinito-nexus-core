# Matomo

## Description

Experience the power of Matomo, an innovative open-source analytics platform that delivers real-time insights, robust visitor tracking, and privacy-first features to elevate your website performance. Dive into actionable data with unmatched precision and clarity.

## Overview

This role deploys Matomo using Docker, automating the setup of your analytics platform along with its underlying database. With support for health checks, persistent storage for configuration and data, and integration with an NGINX reverse proxy, Matomo is configured to provide reliable and scalable analytics for your digital presence.

## Features

- **Real-Time Analytics:** Monitor visitor activity and generate detailed insights instantly.
- **Robust Tracking:** Track user interactions across your website with comprehensive analytics tools.
- **Privacy-First:** Enjoy a self-hosted solution that prioritizes data ownership and privacy.
- **Customizable Setup:** Configure database connections, admin credentials, and server settings via environment variables and Matomo's `config/config.ini.php`, which the role patches on every deploy.
- **Administrator Password:** The superuser password converges to the configured administrator's password on every deploy.
- **Single Sign-On:** With Keycloak deployed, the login page offers a Keycloak sign-in through the GPL-3.0 [RebelOIDC](https://github.com/Digitalist-Open-Cloud/Matomo-Plugin-RebelOIDC) plugin, which the custom image ships and the deploy activates. The OIDC username claim names the Matomo login, an existing account with that login is linked on first sign-in, and the sign-out also ends the Keycloak session. Signup is off, so only accounts the deploy provisioned can sign in. The local superuser keeps its password login.
- **Role Mapping:** The RBAC roles `view`, `write` and `admin` grant that access on every tracked website, and `administrator` grants superuser access. Every deploy creates an account for each member, assigns the access and takes it from every other account; the local superuser is never touched. A membership change therefore takes effect at the next deploy, and a website added later gets its access at the next deploy as well.
- **Proxy Scheme:** Matomo reads the scheme from `X-Forwarded-Proto`, so it builds `https` URLs behind the TLS-terminating proxy.
- **Corporate Design:** The InfinitoDesign theme plugin maps Matomo's theme colors onto the design tokens and ships the logo set; the administrator and the login page follow the browser color scheme. Both are removed when `design` is off.
- **Scalable Deployment:** Use Docker to ensure your analytics platform can grow with your traffic demands.
- **Version Upgrades:** When the pinned image ships a newer Matomo than the data volume holds, the deploy installs that release into the volume, keeps `config/config.ini.php`, `misc/user/` and Marketplace plugins, and runs `core:update`; a volume newer than the image stops the deploy.

## Further Resources

- [Matomo Official Website](https://matomo.org/)
- [Corporate design review: screenshots in light, dark, desktop and mobile](https://claude.ai/artifact/8ox3o13gTQiCRE9nnvBPCB)

## Persona contract opt-outs

This role declares `PERSONA_ADMINISTRATOR_BLOCKED` and `PERSONA_BIBER_BLOCKED` in `templates/playwright.env.j2`.

- **Administrator:** blocked only with `sso` off. The shared native login looks the username field up by the names `username`, `email` and `login`, while Matomo names it `form_login`, so the persona would submit the password alone. `files/playwright/auth.spec.js` drives the native form of the local superuser. With `sso` on the persona clicks the RebelOIDC button and signs in through Keycloak; `files/playwright/addons/rebeloidc.spec.js` additionally asserts the superuser access and the Keycloak sign-out.
- **Biber:** Matomo admits only members of its RBAC roles. Biber holds none, so the deploy provisions no account for biber and the Keycloak login ends without a Matomo session. `files/playwright/auth.spec.js` owns that deny-probe, the provider-side assertion the persona helpers no longer duplicate.
