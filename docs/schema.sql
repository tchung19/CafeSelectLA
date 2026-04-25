-- CafeSelect — Supabase Schema
-- Run this in your Supabase project's SQL Editor before running the pipeline.

-- 1. Enable pgvector for semantic search
create extension if not exists vector;

-- 2. Create cafes table
create table if not exists public.cafes (
  -- Identity
  place_id          text primary key,
  name              text not null,
  address           text,
  neighborhood      text,
  region            text,
  latitude          double precision,
  longitude         double precision,
  google_maps_url   text,
  website           text,
  phone             text,
  primary_type      text,
  business_status   text,

  -- Hours
  hours_mon         text,
  hours_tue         text,
  hours_wed         text,
  hours_thu         text,
  hours_fri         text,
  hours_sat         text,
  hours_sun         text,
  open_weekends     boolean,
  open_after_5pm    boolean,

  -- Ratings & summaries
  rating            numeric(3,1),
  review_count      integer,
  price_level       text,
  editorial_summary text,
  review_summary    text,
  generative_summary text,

  -- Google amenities
  outdoor_seating   boolean,
  dine_in           boolean,
  takeout           boolean,
  delivery          boolean,
  reservable        boolean,
  dogs_allowed      boolean,
  good_for_children boolean,
  restroom          boolean,
  live_music        boolean,

  -- Food & drink served
  serves_coffee     boolean,
  serves_breakfast  boolean,
  serves_brunch     boolean,
  serves_lunch      boolean,
  serves_dinner     boolean,
  serves_dessert    boolean,
  serves_vegetarian boolean,

  -- Parking
  parking_free      boolean,
  parking_paid      boolean,
  parking_street    boolean,
  parking_garage    boolean,

  -- Work & study
  has_outlets       integer,
  outlet_confidence numeric(3,2),
  outlet_mentions   integer,
  wifi_quality      integer,
  wifi_confidence   numeric(3,2),
  study_friendly    boolean,
  study_confidence  numeric(3,2),
  laptop_policy     text,
  noise_level       text,
  noise_notes       text,
  solo_friendly     boolean,
  solo_confidence   numeric(3,2),

  -- Space & physical
  seating_types     text[],
  seating_capacity  text,
  seating_comfort   text,
  seating_comfort_notes text,
  space_size        text,
  lighting          text,
  decor_style       text[],
  cleanliness       text,
  has_patio         boolean,
  counter_service   boolean,
  has_display_case  boolean,

  -- Vibe & social
  overall_vibe      text[],
  instagrammable    boolean,
  instagrammable_vision_raw boolean,
  instagram_confidence numeric(3,2),
  good_for_dates    boolean,
  good_for_dates_llm_raw boolean,
  date_score        integer,
  date_confidence   numeric(3,2),
  group_friendly    boolean,
  group_confidence  numeric(3,2),
  best_time_to_visit text,
  staff_friendliness text,
  staff_notes       text,
  price_perception  text,
  price_notes       text,

  -- Food & drink details
  has_matcha        boolean,
  has_avocado_toast boolean,
  has_specialty_coffee boolean,
  has_food_menu     boolean,
  has_vegan_options boolean,
  has_pastries      boolean,
  specialty_drinks  text[],
  signature_items   text[],
  food_visible      text[],
  drinks_visible    text[],

  -- Photos
  photo_urls        text[],
  hero_photo_url    text,
  photo_types       text[],

  -- AI / semantic search
  ai_summary        text,
  top_attributes    text[],
  embedding         vector(1536),

  -- Metadata
  created_at        timestamptz default now(),
  updated_at        timestamptz default now()
);

-- 3. Indexes
create index if not exists cafes_neighborhood_idx on public.cafes (neighborhood);
create index if not exists cafes_region_idx on public.cafes (region);
create index if not exists cafes_rating_idx on public.cafes (rating desc);
create index if not exists cafes_embedding_idx on public.cafes
  using ivfflat (embedding vector_cosine_ops) with (lists = 10);
