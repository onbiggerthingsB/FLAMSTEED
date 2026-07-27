/** In-memory gateway client: no cookies, storage, or third-party requests. */
export interface Tok {
  token: string;
  exp: number;
  tier: 'basic' | 'advanced';
}

export interface EmbedClient {
  getToken(): Promise<Tok>;
  getJson<T>(path: string): Promise<T>;
}

export function createClient(
  endpoint: string,
  publisherId: string,
  frameKey?: string,
): EmbedClient {
  const base = endpoint.replace(/\/+$/, '');
  let token: Tok | null = null;
  let inFlightToken: Promise<Tok> | null = null;
  const frameQuery = frameKey ? `&k=${encodeURIComponent(frameKey)}` : '';

  async function fetchToken(): Promise<Tok> {
    const response = await fetch(
      `${base}/v1/token?pid=${encodeURIComponent(publisherId)}${frameQuery}`,
      { credentials: 'omit' },
    );
    if (!response.ok) throw new Error(`token refused: ${response.status}`);
    return (await response.json()) as Tok;
  }

  function getToken(): Promise<Tok> {
    if (token && token.exp * 1000 - Date.now() > 60_000) {
      return Promise.resolve(token);
    }
    if (!inFlightToken) {
      inFlightToken = fetchToken()
        .then((fresh) => {
          token = fresh;
          return fresh;
        })
        .finally(() => {
          inFlightToken = null;
        });
    }
    return inFlightToken;
  }

  async function getJson<T>(path: string): Promise<T> {
    for (let attempt = 0; attempt < 2; attempt += 1) {
      const current = await getToken();
      const separator = path.includes('?') ? '&' : '?';
      const response = await fetch(
        `${base}${path}${separator}t=${encodeURIComponent(current.token)}${frameQuery}`,
        { credentials: 'omit' },
      );
      if (response.ok) return (await response.json()) as T;
      if ((response.status === 401 || response.status === 403) && attempt === 0) {
        token = null;
        continue;
      }
      throw new Error(`gateway ${response.status} for ${path}`);
    }
    throw new Error('gateway retry exhausted');
  }

  return { getToken, getJson };
}
