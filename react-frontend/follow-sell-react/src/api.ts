export const API_BASE = window.location.origin;

export async function createTaskBySkuText(skuText: string) {
  const res = await fetch(`${API_BASE}/api/tasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sku_text: skuText }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchTasks() {
  const res = await fetch(`${API_BASE}/api/tasks`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchActiveClients() {
  const res = await fetch(`${API_BASE}/api/clients/active`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
