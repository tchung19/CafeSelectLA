'use client';

const EXAMPLES = [
  'quiet spot to study with outlets',
  'aesthetic cafe good for a date',
  'open late with matcha',
  'outdoor patio in Venice',
  'specialty coffee, not too loud',
  'dog-friendly cafe in Santa Monica',
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
