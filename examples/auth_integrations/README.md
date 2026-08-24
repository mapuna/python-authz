# Auth Integration Recipes

`authz` answers "is this subject allowed to do this," not "who is this
subject." `requires()` takes `get_subject` as a plain function you
supply, and the library stays out of authentication entirely (see
[`docs/fastapi_integration.md`](../../docs/fastapi_integration.md)). Most
apps resolve "who is the current user" one of two ways, and these two
recipes are working, runnable references for each:

- **[`jwt/`](jwt/README.md)**: your app issues and verifies its own
  tokens. Reach for this when you want a self-contained login flow with
  no external identity provider.
- **[`oauth2/`](oauth2/README.md)**: your app delegates login to an
  external provider (Google, GitHub, Auth0, your company's SSO, ...) via
  the standard Authorization Code flow. Reach for this when a third party
  is the source of truth for who your users are.

Each recipe is a small, standalone app, deliberately separate from
[`examples/sample_app/`](../sample_app/README.md), so it demonstrates
only the authentication mechanism.

SAML was considered and left out on purpose. Unlike OAuth2/JWT, it needs
system-level dependencies (`python3-saml` requires `xmlsec1`/`libxml2`)
and a real identity provider to demonstrate at all, a different order of
complexity than "clone and run." If you need SAML specifically, the same
`get_subject` pattern these recipes show still applies; you'll just be
wiring it to whatever SAML library and identity provider your
organization already uses.
