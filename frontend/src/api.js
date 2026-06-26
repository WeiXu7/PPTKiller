const API_BASE = import.meta.env.VITE_API_URL || "/api/v1";
const TOKEN_KEY = "pptkiller_token";

function absolutizeApiUrl(path) {
  if (/^https?:\/\//i.test(path)) return path;
  const base = API_BASE.endsWith("/api/v1") ? API_BASE.slice(0, -"/api/v1".length) : "";
  return `${base}${path}`;
}

export function getToken() {
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
}

async function request(path, options = {}) {
  const token = getToken();
  const headers = new Headers(options.headers || {});
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!response.ok) {
    let message = `请求失败（${response.status}）`;
    try {
      const payload = await response.json();
      message = payload.detail || message;
    } catch {
      // Keep the HTTP fallback.
    }
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  if (response.status === 204) return null;
  return response.json();
}

export const api = {
  register: (payload) => request("/auth/register", { method: "POST", body: JSON.stringify(payload) }),
  login: (payload) => request("/auth/login", { method: "POST", body: JSON.stringify(payload) }),
  me: () => request("/me"),
  projects: () => request("/projects"),
  createProject: (payload) => request("/projects", { method: "POST", body: JSON.stringify(payload) }),
  sessions: (projectId) => request(`/projects/${projectId}/sessions`),
  session: (sessionId) => request(`/sessions/${sessionId}`),
  startSession: (projectId, payload) =>
    request(`/projects/${projectId}/sessions`, { method: "POST", body: JSON.stringify(payload) }),
  approve: (sessionId, payload) =>
    request(`/sessions/${sessionId}/approve`, { method: "POST", body: JSON.stringify(payload) }),
  revise: (sessionId, instruction) =>
    request(`/sessions/${sessionId}/revise`, { method: "POST", body: JSON.stringify({ instruction }) }),
  updateSlide: (sessionId, number, payload) =>
    request(`/sessions/${sessionId}/slides/${number}`, { method: "PATCH", body: JSON.stringify(payload) }),
  updateSlideImage: (sessionId, number, payload) =>
    request(`/sessions/${sessionId}/slides/${number}/image`, { method: "PATCH", body: JSON.stringify(payload) }),
  searchImages: (query, limit = 8) => request(`/research/images?q=${encodeURIComponent(query)}&limit=${limit}`),
  exportManifest: (sessionId) => request(`/sessions/${sessionId}/export/manifest`),
  upload: async (projectId, file, description = "") => {
    const form = new FormData();
    form.append("file", file);
    form.append("description", description);
    return request(`/projects/${projectId}/assets`, { method: "POST", body: form });
  },
  exportUrl: (sessionId) => `${API_BASE}/sessions/${sessionId}/export`,
};

export async function protectedBlobUrl(path) {
  const response = await fetch(absolutizeApiUrl(path), {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || "资源加载失败");
  }
  return URL.createObjectURL(await response.blob());
}

export async function downloadExport(sessionId, filename) {
  const response = await fetch(api.exportUrl(sessionId), {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || "导出失败");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${filename || "PPTKiller"}.pptx`;
  anchor.click();
  URL.revokeObjectURL(url);
}
