ARG KEYCLOAK_ADAPTER_BASE_IMAGE
ARG KEYCLOAK_ADAPTER_BASE_VERSION
FROM ${KEYCLOAK_ADAPTER_BASE_IMAGE}:${KEYCLOAK_ADAPTER_BASE_VERSION}

ARG KEYCLOAK_ADAPTER_SOURCE_URL
WORKDIR /app
ADD --chmod=644 ${KEYCLOAK_ADAPTER_SOURCE_URL}/config.ts /app/config.ts
ADD --chmod=644 ${KEYCLOAK_ADAPTER_SOURCE_URL}/adapter.ts /app/adapter.ts
COPY --chmod=644 context.ts /app/context.ts
RUN deno cache /app/adapter.ts

USER deno
CMD ["deno", "run", "--allow-net", "--allow-env", "/app/adapter.ts"]
