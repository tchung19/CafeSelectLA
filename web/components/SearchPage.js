'use client';

import { useState, useEffect } from 'react';
import SearchBar from './SearchBar';
import NeighborhoodPills from './NeighborhoodPills';
import ExampleQueries from './ExampleQueries';
import CafeCard from './CafeCard';
import { searchCafes, fetchNeighborhoods } from '@/lib/api';

export default function SearchPage() {
  const [query, setQuery] = useState('');
  const [neighborhood, setNeighborhood] = useState(null);
  const [neighborhoods, setNeighborhoods] = useState([]);

  useEffect(() => {
    fetchNeighborhoods().then(setNeighborhoods);
  }, []);
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function handleSearch() {
    const fullQuery = neighborhood ? `${query} in ${neighborhood}` : query;
    if (!fullQuery.trim()) return;

    setLoading(true);
    setError(null);

    try {
      const data = await searchCafes(fullQuery);
      setResults(data.results);
    } catch {
      setError('Something went wrong. Make sure the API is running.');
    } finally {
      setLoading(false);
    }
  }

  function handleExampleSelect(q) {
    setQuery(q);
  }

  function handleNeighborhoodSelect(n) {
    setNeighborhood(n);
  }

  const hasResults = results !== null;

  return (
    <main className="mx-auto max-w-5xl px-4 py-12 sm:px-6">
      {/* Header */}
      <div className="mb-8 text-center">
        <h1 className="text-3xl font-bold tracking-tight text-gray-900">CafeSelect</h1>
        <p className="mt-2 text-gray-500">
          Describe what you need. Get cafes that actually match.
        </p>
      </div>

      {/* Search controls */}
      <div className="flex flex-col gap-4">
        <SearchBar
          value={query}
          onChange={setQuery}
          onSubmit={handleSearch}
          loading={loading}
        />
        <NeighborhoodPills
          neighborhoods={neighborhoods}
          selected={neighborhood}
          onSelect={handleNeighborhoodSelect}
        />
      </div>

      {/* Empty state — example queries */}
      {!hasResults && !loading && (
        <div className="mt-10">
          <p className="mb-3 text-sm text-gray-400">Try one of these</p>
          <ExampleQueries onSelect={handleExampleSelect} />
        </div>
      )}

      {/* Error */}
      {error && (
        <p className="mt-6 text-sm text-red-500">{error}</p>
      )}

      {/* Results */}
      {hasResults && (
        <div className="mt-8">
          {results.length === 0 ? (
            <div className="text-center py-16 text-gray-400">
              <p className="text-lg">No cafes found.</p>
              <p className="text-sm mt-1">Try removing a filter or broadening your search.</p>
            </div>
          ) : (
            <>
              <p className="mb-4 text-sm text-gray-400">{results.length} cafe{results.length !== 1 ? 's' : ''} found</p>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {results.map((cafe) => (
                  <CafeCard key={cafe.place_id} cafe={cafe} />
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </main>
  );
}
