'use client';

const EXAMPLES = [
  'open till 6pm with matcha',
  'quiet spot good for studying',
  'cafe with outdoor seating',
];

export default function ExampleQueries({ onSelect }) {
  return (
    <div className="flex flex-wrap gap-2">
      {EXAMPLES.map((q) => (
        <button
          key={q}
          onClick={() => onSelect(q)}
          className="rounded-full border border-dashed border-gray-300 px-3 py-1 text-sm text-gray-500 transition-colors hover:border-gray-500 hover:text-gray-700"
        >
          {q}
        </button>
      ))}
    </div>
  );
}
