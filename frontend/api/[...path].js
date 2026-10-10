const MAX_REQUEST_BYTES = 1_000_000;

export const config = {
  api: { bodyParser: false },
  maxDuration: 60,
};

export default async function handler(request, response) {
  const pathname = new URL(request.url, 'http://localhost').pathname;
  if (pathname !== '/api' && !pathname.startsWith('/api/')) {
    response.statusCode = 404;
    response.end('Not found');
    return;
  }
  if (!['GET', 'POST'].includes(request.method || '')) {
    response.setHeader('Allow', 'GET, POST');
    response.statusCode = 405;
    response.end('Method not allowed');
    return;
  }

  const backendUrl = process.env.BACKEND_URL;
  if (!backendUrl) {
    response.statusCode = 503;
    response.end('Internal API binding is unavailable');
    return;
  }

  try {
    const inbound = new URL(request.url, 'http://localhost');
    const target = new URL(`${inbound.pathname}${inbound.search}`, backendUrl);
    const headers = new Headers();
    for (const name of ['accept', 'content-type']) {
      const value = request.headers[name];
      if (typeof value === 'string') headers.set(name, value);
    }

    let body;
    if (request.method === 'POST') {
      const chunks = [];
      let size = 0;
      for await (const chunk of request) {
        size += chunk.length;
        if (size > MAX_REQUEST_BYTES) {
          response.statusCode = 413;
          response.end('Request too large');
          return;
        }
        chunks.push(chunk);
      }
      body = Buffer.concat(chunks, size);
    }

    const upstream = await fetch(target, {
      method: request.method,
      headers,
      body,
      redirect: 'manual',
      signal: AbortSignal.timeout(55_000),
    });
    if (upstream.status >= 300 && upstream.status < 400) {
      response.statusCode = 502;
      response.end('Internal API returned an unexpected redirect');
      return;
    }

    response.statusCode = upstream.status;
    for (const name of ['content-type', 'cache-control', 'retry-after']) {
      const value = upstream.headers.get(name);
      if (value) response.setHeader(name, value);
    }
    response.end(Buffer.from(await upstream.arrayBuffer()));
  } catch {
    response.statusCode = 502;
    response.end('Internal API request failed');
  }
}
