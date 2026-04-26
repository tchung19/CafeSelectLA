'use client';

function Badge({ label }) {
  return (
    <span className="inline-flex items-center rounded-full bg-gray-100 px-2.5 py-0.5 text-xs text-gray-600">
      {label}
    </span>
  );
}

function noiseLabel(level) {
  if (!level) return null;
  return { quiet: '🔇 Quiet', moderate: '🔉 Moderate', loud: '🔊 Loud' }[level] ?? level;
}

export default function CafeCard({ cafe }) {
  const photoUrl = typeof cafe.hero_photo_url === 'string' && cafe.hero_photo_url
    ? cafe.hero_photo_url.startsWith('https://')
      ? cafe.hero_photo_url
      : `/api/photo?r=${encodeURIComponent(cafe.hero_photo_url)}`
    : null;

  const vibes = Array.isArray(cafe.overall_vibe) ? cafe.overall_vibe.slice(0, 3) : [];

  return (
    <div className="flex flex-col rounded-2xl border border-gray-100 bg-white shadow-sm overflow-hidden">
      {/* Photo */}
      <div className="h-44 w-full bg-gray-100 flex items-center justify-center text-gray-300 text-sm">
        {photoUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={photoUrl}
            alt={cafe.name}
            className="h-full w-full object-cover"
          />
        ) : (
          <span>No photo</span>
        )}
      </div>

      <div className="flex flex-col gap-3 p-4">
        {/* Name + location */}
        <div>
          <div className="flex items-start justify-between gap-2">
            <h2 className="font-semibold text-gray-900 leading-snug">{cafe.name}</h2>
            {cafe.rating && (
              <span className="shrink-0 text-sm text-gray-500">
                ★ {cafe.rating}
                {cafe.review_count ? ` (${cafe.review_count})` : ''}
              </span>
            )}
          </div>
          {cafe.neighborhood && (
            <p className="text-xs text-gray-400 mt-0.5">{cafe.neighborhood}</p>
          )}
        </div>

        {/* Vibe tags */}
        {vibes.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {vibes.map((v) => (
              <span key={v} className="rounded-full bg-amber-50 px-2.5 py-0.5 text-xs text-amber-700">
                {v}
              </span>
            ))}
          </div>
        )}

        {/* Attribute badges */}
        <div className="flex flex-wrap gap-1.5">
          {cafe.study_friendly && <Badge label="💻 Study-friendly" />}
          {cafe.has_outlets > 0 && <Badge label="🔌 Outlets" />}
          {cafe.has_patio && <Badge label="🌿 Patio" />}
          {cafe.has_matcha && <Badge label="🍵 Matcha" />}
          {cafe.noise_level && <Badge label={noiseLabel(cafe.noise_level)} />}
        </div>

        {/* Summary */}
        {cafe.generative_summary && (
          <p className="text-sm text-gray-500 line-clamp-2">{cafe.generative_summary}</p>
        )}

        {/* Links */}
        <div className="flex gap-3 text-xs mt-auto pt-1">
          {cafe.google_maps_url && (
            <a
              href={cafe.google_maps_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-500 hover:underline"
            >
              Google Maps
            </a>
          )}
          {cafe.website && (
            <a
              href={cafe.website}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-500 hover:underline"
            >
              Website
            </a>
          )}
        </div>
      </div>
    </div>
  );
}
