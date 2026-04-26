'use client';

export default function NeighborhoodPills({ neighborhoods, selected, onSelect }) {
  if (!neighborhoods || neighborhoods.length === 0) return null;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-2">
        {neighborhoods.map((n) => (
          <button
            key={n}
            onClick={() => onSelect(selected === n ? null : n)}
            className={`rounded-full border px-3 py-1 text-sm transition-colors ${
              selected === n
                ? 'border-gray-900 bg-gray-900 text-white'
                : 'border-gray-200 bg-white text-gray-600 hover:border-gray-400'
            }`}
          >
            {n}
          </button>
        ))}
      </div>
      <p className="text-xs text-gray-400">More West LA neighborhoods coming soon.</p>
    </div>
  );
}
