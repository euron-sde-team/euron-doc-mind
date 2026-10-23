# ADR 0007: One web image for every environment, configured at runtime

## Status

Accepted.

## Context

The web app needs to know where the API is (`https://api.<domain>` on AWS,
`http://localhost:8110` locally) and the product name. Next.js inlines `NEXT_PUBLIC_*`
variables at build time, which would mean one image per environment: the image tested in CI
would not be the image deployed, and a domain change would need a rebuild.

## Decision

- The web app reads its configuration from `/env.js`, a route handler
  (`apps/web/src/app/env.js/route.ts`) that serialises `API_URL` and `PRODUCT_NAME` from the
  server's environment into `window.__DOCMIND__` at request time. The root layout loads it
  with `strategy="beforeInteractive"`, before the app's own scripts.
- The serialiser escapes `<` so the script stays inert inside HTML; values are read from
  the environment only, never from the request.
- The image is built once (`output: "standalone"`), runs as the unprivileged `node` user,
  and is configured by the task definition or Compose: `API_URL` and `PRODUCT_NAME`.
- The ALB health check for the web service requests `/env.js`, which proves the server
  renders.

## Consequences

Positive:

- The same image digest runs locally, in `aws-dev` and in `aws-prod`; promotion is a tag,
  not a rebuild.
- Changing the API domain or the product name is a configuration change.

Trade-offs:

- One extra small request on every full page load (served with `Cache-Control: no-store`,
  so a configuration change applies at once).
- Configuration is visible to the browser by design, so only public values may go there;
  secrets never do.

## Alternatives considered

- **`NEXT_PUBLIC_*` at build time.** The Next.js default; one image per environment.
- **A same-origin API proxy in Next.js.** Hides the API host, but routes every streamed
  answer through the web tier and doubles its load.
