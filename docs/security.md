# SerpApi key security boundary

VersionVerdict keeps `SERPAPI_KEY` in the backend process environment. A local root `.env` can populate that environment without overriding existing process values. The browser does not receive the key. `/api/health` and `/api/capabilities` report only whether a key is configured.

For each uncached live search, the backend sends the key as SerpApi's `api_key` request parameter to the fixed `https://serpapi.com/search.json` endpoint. TLS certificate verification stays enabled, and HTTP redirects are disabled so the credential cannot be forwarded to a different host. SerpApi must receive the key to authenticate the request.

Provider errors return fixed messages. Search responses sent to the browser and the persistent cache omit credentials and provider request metadata. The cache key excludes the credential. Tests use a synthetic key to check API responses, cache contents, and redirect behavior; they do not spend searches.

## Deployment boundary

Store the key in the hosting provider's server-side secret settings or enter it into the backend shell with the masked `read -s` command in the README. Do not paste a real key into chat, source code, browser developer tools, a `VITE_*` variable, a URL that you share, or screenshots.

The machine administrator and anyone who can inspect its running backend or secret store can access the credential. SerpApi receives it for authenticated searches. A public, unauthenticated deployment does not expose the key in its responses, but visitors can call its search endpoint and use the configured application allocation. Keep the default allocation limited, keep the SQLite ledger persistent, and use host-level access controls if a private service is required.

VersionVerdict does not provide user accounts or authenticate visitors. Do not treat the application allocation as an account-wide spending cap or as access control.

## General source inspection

General stack search fetches only bounded public HTTPS content. It rejects local/private addresses and URL credentials, checks DNS results, pins validated destinations, and revalidates redirects. Source requests do not inherit SerpApi authentication. A restrictive egress proxy or an inaccessible source results in missing evidence and an uncertain verdict. Uploaded manifests and retrieved examples are parsed as data; the service does not execute them.
