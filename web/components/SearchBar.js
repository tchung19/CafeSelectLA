'use client';

export default function SearchBar({ value, onChange, onSubmit, loading }) {
  function handleKeyDown(e) {
    if (e.key === 'Enter') onSubmit();
  }

  return (
    <div className="flex gap-2 w-full">
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="e.g. quiet spot to work in Westwood with outlets open late"
        className="flex-1 rounded-xl border border-gray-200 px-4 py-3 text-base shadow-sm outline-none focus:border-gray-400 focus:ring-0 placeholder:text-gray-400"
      />
      <button
        onClick={onSubmit}
        disabled={loading || !value.trim()}
        className="rounded-xl bg-gray-900 px-5 py-3 text-sm font-medium text-white transition-colors hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {loading ? 'Searching…' : 'Search'}
      </button>
    </div>
  );
}
