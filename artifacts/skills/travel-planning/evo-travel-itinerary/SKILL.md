---
name: evo-travel-itinerary
description: "Build database-grounded travel itineraries from structured CSV data. Provides search functions and an end-to-end builder that assembles a multi-day itinerary satisfying caller-supplied constraints like budget, accommodation policies, cuisine preferences, and transport mode restrictions."
---

# Travel Itinerary Builder Skill

## Overview
This skill builds travel itineraries grounded in structured database files (CSV).
It provides search functions for cities, accommodations, restaurants, attractions,
and distances, plus an end-to-end builder that assembles a complete multi-day
itinerary. All task-specific parameters (origin, destinations, state, dates,
budget, policy filters, cuisines, transport mode) are caller-supplied.

## Quick Start

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-travel-itinerary/scripts')
from itinerary_builder import build_itinerary, validate_itinerary

# All parameters come from the task instruction — nothing is hardcoded.
# Replace these placeholder values with actual task requirements.
result = build_itinerary(
    origin='<ORIGIN_CITY>',
    destination_cities=['<CITY_A>', '<CITY_B>', '<CITY_C>'],
    destination_state='<STATE>',
    start_date='<YYYY-MM-DD>',
    num_days=7,
    num_travelers=2,
    budget=5000,
    cuisines=['<CUISINE_1>', '<CUISINE_2>'],
    accommodation_exclusion_keywords=['<POLICY_KEYWORD>'],
    accommodation_policy_column=None,  # auto-discovered from schema
    transport_mode='Self-driving',
    output_path='/app/output/itinerary.json'
)

errors = validate_itinerary('/app/output/itinerary.json')
if not errors:
    print('Itinerary valid!')
```

## Search Functions

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-travel-itinerary/scripts')
from search_tools import (
    search_cities, search_accommodations, search_restaurants,
    search_attractions, search_distances, search_flights
)

# Search cities in a state
cities = search_cities(state='<STATE_NAME>')

# Accommodations with policy exclusion
accs = search_accommodations(
    city='<CITY>',
    exclusion_keywords=['<POLICY_KEYWORD>'],
    min_occupancy=2
)

# Restaurants by cuisine
rests = search_restaurants(city='<CITY>', cuisine='<CUISINE>')

# Attractions
attrs = search_attractions(city='<CITY>')

# Driving distances
dists = search_distances(origin='<ORIGIN>', destination='<DEST>')
```

## Key Design Decisions
- **No hardcoded values**: All cities, dates, policies, cuisines, and constraints
  are caller-supplied parameters derived from the task instruction.
- **Policy filtering**: The caller passes exclusion keywords (e.g. policy
  restrictions that conflict with party needs) and optionally the column name;
  the skill auto-discovers the policy column if not specified.
- **Cuisine coverage**: The builder ensures each requested cuisine appears at
  least once across the trip by prioritizing cuisine-matched restaurants first.
- **No duplicates**: A global used-names set prevents the same restaurant from
  appearing twice in the itinerary.
- **Budget awareness**: Selects cheapest qualifying accommodations and
  cost-effective restaurants to stay within the caller-supplied budget.
- **Route structure**: For 3 destination cities over 7 days, allocates 2 nights
  per city with travel days between them.
