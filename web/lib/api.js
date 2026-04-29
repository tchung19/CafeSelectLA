export async function fetchNeighborhoods() {
  const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/neighborhoods`);
  if (!res.ok) return [];
  const data = await res.json();
  // Returns [{name, count}, ...]
  return data.neighborhoods ?? [];
}

export async function searchCafes(query, neighborhoods = []) {
  const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, neighborhoods }),
  });
  if (!res.ok) throw new Error('Search failed');
  return res.json();
}
