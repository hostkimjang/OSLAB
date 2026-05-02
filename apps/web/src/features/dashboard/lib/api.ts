export async function apiGet<T>(url: string): Promise<T> {
  const response = await fetch(url, { credentials: "include" });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export async function apiText(url: string): Promise<string> {
  const response = await fetch(url, { credentials: "include" });
  if (!response.ok) throw new Error(await response.text());
  return response.text();
}

export async function apiPost<T = any>(url: string, body: any, method = "POST"): Promise<T> {
  const response = await fetch(url, {
    method,
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export async function apiUpload<T = any>(url: string, file: File): Promise<T> {
  const formData = new FormData();
  formData.append("file", file);
  return submitUpload<T>(url, formData);
}

export interface UploadProgress {
  loaded: number;
  total: number;
  percent: number | null;
}

export async function apiUploadWithProgress<T = any>(url: string, file: File, onProgress?: (progress: UploadProgress) => void): Promise<T> {
  const formData = new FormData();
  formData.append("file", file);
  return submitUpload<T>(url, formData, onProgress);
}

export async function apiUploadFiles<T = any>(url: string, files: File[], onProgress?: (progress: UploadProgress) => void): Promise<T> {
  const formData = new FormData();
  for (const file of files) {
    const relativePath = (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name;
    formData.append("files", file, relativePath);
    formData.append("paths", relativePath);
  }
  return submitUpload<T>(url, formData, onProgress);
}

export function getApiBaseUrl(): string {
  if (typeof window === "undefined") return "";
  const protocol = window.location.protocol;
  const hostname = window.location.hostname || "127.0.0.1";
  return `${protocol}//${hostname}:3001`;
}

function submitUpload<T>(url: string, formData: FormData, onProgress?: (progress: UploadProgress) => void): Promise<T> {
  const targetUrl = normalizeUploadUrl(url);
  if (!onProgress) {
    return fetch(targetUrl, {
      method: "POST",
      credentials: "include",
      body: formData,
    }).then(async (response) => {
      if (!response.ok) throw new Error(await response.text());
      return response.json();
    });
  }

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", targetUrl);
    xhr.withCredentials = true;
    xhr.upload.onprogress = (event) => {
      onProgress({
        loaded: event.loaded,
        total: event.lengthComputable ? event.total : 0,
        percent: event.lengthComputable && event.total ? Math.min(100, Math.round((event.loaded / event.total) * 100)) : null,
      });
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as T);
        } catch (error) {
          reject(error);
        }
        return;
      }
      reject(new Error(xhr.responseText || `${xhr.status} ${xhr.statusText}`));
    };
    xhr.onerror = () => reject(new Error("Upload request failed"));
    xhr.onabort = () => reject(new Error("Upload request was cancelled"));
    xhr.send(formData);
  });
}

function normalizeUploadUrl(url: string): string {
  if (typeof window === "undefined" || !url.startsWith("/api/")) return url;
  return `${getApiBaseUrl()}${url}`;
}
