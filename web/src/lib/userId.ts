const STORAGE_KEY = "lucas_user_id";

function generateId(): string {
  return crypto.randomUUID();
}

export function getUserId(): string {
  let id = localStorage.getItem(STORAGE_KEY);
  if (!id) {
    id = generateId();
    localStorage.setItem(STORAGE_KEY, id);
  }
  return id;
}

export function userHeaders(): Record<string, string> {
  return { "X-User-Id": getUserId() };
}
