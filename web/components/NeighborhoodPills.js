'use client';

export default function NeighborhoodPills({ neighborhoods, selected, onSelect }) {
  if (!neighborhoods || neighborhoods.length === 0) return null;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-2">
        {neighborhoods.map((n) => {
          const isSelected = selected?.name === n.name;
          return (
            <button
              key={n.name}
              onClick={() => onSelect(isSelected ? null : n)}
              className={`rounded-full border px-3 py-1 text-sm transition-colors ${
                isSelected
                  ? 'border-amber-700 bg-amber-700 text-white'
                  : 'border-gray-200 bg-white text-gray-600 hover:border-amber-400 dark:bg-transparent dark:text-gray-400 dark:border-gray-700 dark:hover:border-amber-500'
              }`}
            >
              {n.name}
              <span className={`ml-1.5 text-xs font-normal ${isSelected ? 'text-amber-200' : 'text-gray-400 dark:text-gray-500'}`}>
                {n.count}
              </span>
            </button>
          );
        })}
      </div>
      <p className="text-xs text-gray-400">More West LA neighborhoods coming soon.</p>
    </div>
  );
}
