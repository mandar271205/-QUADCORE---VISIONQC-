// Share overlapping reads (including React StrictMode mounts). Only product
// lists get a brief cache; live inspection/history/training results stay fresh.
const pending = new Map<string, Promise<unknown>>();
const cached = new Map<string, { value: unknown; expires: number }>();
let revision = 0;

export function invalidateReads(): void {
  revision += 1;
  cached.clear();
  pending.clear();
}

export function readShared<T>(key: string, load: () => Promise<T>, ttl = 0): Promise<T> {
  const entry = cached.get(key);
  if (entry && entry.expires > Date.now()) return Promise.resolve(entry.value as T);
  const existing = pending.get(key);
  if (existing) return existing as Promise<T>;
  const version = revision;
  const request = load().then(value => {
    if (ttl > 0 && version === revision) cached.set(key, { value, expires: Date.now() + ttl });
    return value;
  }).finally(() => {
    if (pending.get(key) === request) pending.delete(key);
  });
  pending.set(key, request);
  return request;
}
