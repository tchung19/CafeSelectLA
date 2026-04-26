import { NextResponse } from 'next/server';

export async function GET(request) {
  const { searchParams } = new URL(request.url);
  const resource = searchParams.get('r');
  if (!resource) return NextResponse.json({ error: 'missing r' }, { status: 400 });

  const apiKey = process.env.GOOGLE_PLACES_API_KEY;
  const url = `https://places.googleapis.com/v1/${resource}/media?maxWidthPx=800&key=${apiKey}&skipHttpRedirect=true`;

  try {
    const res = await fetch(url);
    if (!res.ok) return NextResponse.json({ error: 'photo not found' }, { status: 404 });
    const data = await res.json();
    if (!data.photoUri) return NextResponse.json({ error: 'no photo uri' }, { status: 404 });
    return NextResponse.redirect(data.photoUri);
  } catch {
    return NextResponse.json({ error: 'failed' }, { status: 500 });
  }
}
