export async function fetchJsonRpc(method: string, params: any = {}) {
  const response = await fetch('/mcp/tools', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      jsonrpc: '2.0',
      method,
      params,
      id: Math.random().toString(36).substring(7),
    }),
  });
  const data = await response.json();
  if (data.error) {
    throw new Error(data.error.message);
  }
  return data.result;
}

export async function chatWithAgent(message: string, context: any = {}) {
  const response = await fetch('/api/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ message, context }),
  });
  return await response.json();
}
