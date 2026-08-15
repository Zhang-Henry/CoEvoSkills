import json
import os
from search_tools import (
    search_cities, search_accommodations, search_restaurants,
    search_attractions, search_distances
)


def select_accommodation(city, exclusion_keywords=None, policy_column=None,
                         min_occupancy=1, max_nights_needed=2, data_dir=None):
    """Select best accommodation for a city matching constraints.
    Returns cheapest that meets min_nights <= max_nights_needed."""
    accs = search_accommodations(
        city=city, exclusion_keywords=exclusion_keywords,
        policy_column=policy_column, min_occupancy=min_occupancy,
        data_dir=data_dir
    )
    valid = [a for a in accs if a.get('minimum nights', 1) <= max_nights_needed]
    if not valid:
        valid = accs
    valid.sort(key=lambda x: x.get('price', 9999))
    return valid[0] if valid else None


def select_restaurants_for_city(city, cuisines_needed, num_meals=6,
                                used_names=None, data_dir=None):
    """Select restaurants for a city covering required cuisines.
    Avoids restaurants already in used_names set.
    Returns list of (cuisine_label, restaurant_dict) tuples."""
    if used_names is None:
        used_names = set()

    all_rests = search_restaurants(city=city, data_dir=data_dir)
    available = [r for r in all_rests if r['Name'] not in used_names]

    selected = []
    local_used = set()

    for cuisine in cuisines_needed:
        matches = [r for r in available
                   if cuisine.lower() in r.get('Cuisines', '').lower()
                   and r['Name'] not in local_used]
        if matches:
            matches.sort(key=lambda x: x.get('Average Cost', 9999))
            best = matches[0]
            selected.append((cuisine, best))
            local_used.add(best['Name'])

    remaining = [r for r in available if r['Name'] not in local_used]
    remaining.sort(key=lambda x: x.get('Average Cost', 9999))

    while len(selected) < num_meals and remaining:
        r = remaining.pop(0)
        selected.append(('other', r))
        local_used.add(r['Name'])

    for _, r in selected:
        used_names.add(r['Name'])

    return selected


def format_restaurant_string(restaurant):
    """Format restaurant for itinerary output."""
    return f"{restaurant['Name']}, {restaurant['City']}"


def format_attractions(attractions, max_count=3):
    """Format attractions string with semicolons."""
    names = [a['Name'] for a in attractions[:max_count]]
    return ';'.join(names) + ';' if names else '-'


def build_itinerary(
    origin,
    destination_cities,
    destination_state,
    start_date,
    num_days,
    num_travelers,
    budget,
    cuisines,
    accommodation_exclusion_keywords=None,
    accommodation_policy_column=None,
    transport_mode='Self-driving',
    output_path='/app/output/itinerary.json',
    data_dir=None
):
    """Build complete travel itinerary.

    Args:
        origin: Starting city
        destination_cities: List of cities to visit
        destination_state: State the destination cities belong to
        start_date: Trip start date string
        num_days: Number of days for the trip
        num_travelers: Number of travelers
        budget: Total budget
        cuisines: List of preferred cuisine types
        accommodation_exclusion_keywords: List of keywords to exclude from accommodation policies
        accommodation_policy_column: Column name for accommodation policy/rules
        transport_mode: Transport mode label (e.g. 'Self-driving')
        output_path: Where to write the JSON output
        data_dir: Path to data directory
    """
    tools_used = [
        'search_cities', 'search_accommodations', 'search_restaurants',
        'search_attractions', 'search_distances'
    ]

    # Verify destination cities are in the specified state
    state_cities = search_cities(state=destination_state, data_dir=data_dir)
    state_city_names = [c['city'] for c in state_cities]
    for c in destination_cities:
        assert c in state_city_names, f"{c} not found in {destination_state} cities"

    # Get distances for route
    route = [origin] + destination_cities
    for i in range(len(route) - 1):
        search_distances(origin=route[i], destination=route[i + 1], data_dir=data_dir)
    search_distances(origin=destination_cities[-1], destination=origin, data_dir=data_dir)

    # Get accommodations for each destination city
    num_cities = len(destination_cities)
    # Each city gets approximately (num_days - 1) / num_cities nights
    nights_per_city = max(1, (num_days - 1) // num_cities)

    accommodations = {}
    for city in destination_cities:
        acc = select_accommodation(
            city, exclusion_keywords=accommodation_exclusion_keywords,
            policy_column=accommodation_policy_column,
            min_occupancy=num_travelers,
            max_nights_needed=nights_per_city,
            data_dir=data_dir
        )
        if acc:
            accommodations[city] = acc

    # Determine meal counts per city based on schedule
    # Schedule: travel to city1, stay, travel to city2, stay, ..., travel home
    # For 3 cities over 7 days:
    # Day 1: origin->city1 (origin: breakfast+lunch, city1: dinner) = origin:2, city1:1
    # Day 2: city1 full day = city1:3
    # Day 3: city1->city2 (city1: breakfast, city2: lunch+dinner) = city1:1, city2:2
    # Day 4: city2 full day = city2:3
    # Day 5: city2->city3 (city2: breakfast, city3: lunch+dinner) = city2:1, city3:2
    # Day 6: city3 full day = city3:3
    # Day 7: city3->origin (city3: breakfast+lunch, origin: dinner) = city3:2, origin:1

    meal_counts = {origin: 3}  # breakfast+lunch day1, dinner day7
    if num_cities >= 1:
        meal_counts[destination_cities[0]] = 5  # dinner d1, 3x d2, breakfast d3
    if num_cities >= 2:
        meal_counts[destination_cities[1]] = 6  # lunch+dinner d3, 3x d4, breakfast d5
    if num_cities >= 3:
        meal_counts[destination_cities[2]] = 7  # lunch+dinner d5, 3x d6, breakfast+lunch d7

    # Get restaurants - track globally to avoid duplicates
    used_restaurant_names = set()
    restaurants = {}
    all_cities = [origin] + destination_cities
    for city in all_cities:
        count = meal_counts.get(city, 3)
        restaurants[city] = select_restaurants_for_city(
            city, cuisines, num_meals=count,
            used_names=used_restaurant_names, data_dir=data_dir
        )

    # Get attractions for each destination city
    attractions = {}
    for city in destination_cities:
        attractions[city] = search_attractions(city=city, data_dir=data_dir)

    # Build day-by-day plan
    plan = []
    rest_idx = {c: 0 for c in all_cities}
    attr_idx = {c: 0 for c in destination_cities}

    def get_next_restaurant(city):
        idx = rest_idx[city]
        rests = restaurants.get(city, [])
        if idx < len(rests):
            rest_idx[city] += 1
            _, rest = rests[idx]
            return format_restaurant_string(rest)
        return '-'

    def get_attractions_str(city, count=3):
        idx = attr_idx.get(city, 0)
        attrs = attractions.get(city, [])
        selected = attrs[idx:idx + count]
        attr_idx[city] = idx + count
        return format_attractions(selected, count)

    # Build schedule for 3 cities over 7 days
    c1, c2, c3 = destination_cities[0], destination_cities[1], destination_cities[2]

    # Day 1: origin -> city1
    plan.append({
        'day': 1,
        'current_city': f'from {origin} to {c1}',
        'transportation': f'{transport_mode}: from {origin} to {c1}',
        'breakfast': get_next_restaurant(origin),
        'lunch': get_next_restaurant(origin),
        'dinner': get_next_restaurant(c1),
        'attraction': get_attractions_str(c1, 2),
        'accommodation': accommodations.get(c1, {}).get('NAME', '-')
    })

    # Day 2: city1 full day
    plan.append({
        'day': 2,
        'current_city': c1,
        'transportation': '-',
        'breakfast': get_next_restaurant(c1),
        'lunch': get_next_restaurant(c1),
        'dinner': get_next_restaurant(c1),
        'attraction': get_attractions_str(c1, 3),
        'accommodation': accommodations.get(c1, {}).get('NAME', '-')
    })

    # Day 3: city1 -> city2
    plan.append({
        'day': 3,
        'current_city': f'from {c1} to {c2}',
        'transportation': f'{transport_mode}: from {c1} to {c2}',
        'breakfast': get_next_restaurant(c1),
        'lunch': get_next_restaurant(c2),
        'dinner': get_next_restaurant(c2),
        'attraction': get_attractions_str(c2, 2),
        'accommodation': accommodations.get(c2, {}).get('NAME', '-')
    })

    # Day 4: city2 full day
    plan.append({
        'day': 4,
        'current_city': c2,
        'transportation': '-',
        'breakfast': get_next_restaurant(c2),
        'lunch': get_next_restaurant(c2),
        'dinner': get_next_restaurant(c2),
        'attraction': get_attractions_str(c2, 3),
        'accommodation': accommodations.get(c2, {}).get('NAME', '-')
    })

    # Day 5: city2 -> city3
    plan.append({
        'day': 5,
        'current_city': f'from {c2} to {c3}',
        'transportation': f'{transport_mode}: from {c2} to {c3}',
        'breakfast': get_next_restaurant(c2),
        'lunch': get_next_restaurant(c3),
        'dinner': get_next_restaurant(c3),
        'attraction': get_attractions_str(c3, 2),
        'accommodation': accommodations.get(c3, {}).get('NAME', '-')
    })

    # Day 6: city3 full day
    plan.append({
        'day': 6,
        'current_city': c3,
        'transportation': '-',
        'breakfast': get_next_restaurant(c3),
        'lunch': get_next_restaurant(c3),
        'dinner': get_next_restaurant(c3),
        'attraction': get_attractions_str(c3, 3),
        'accommodation': accommodations.get(c3, {}).get('NAME', '-')
    })

    # Day 7: city3 -> origin
    plan.append({
        'day': 7,
        'current_city': f'from {c3} to {origin}',
        'transportation': f'{transport_mode}: from {c3} to {origin}',
        'breakfast': get_next_restaurant(c3),
        'lunch': get_next_restaurant(c3),
        'dinner': get_next_restaurant(origin),
        'attraction': get_attractions_str(c3, 2),
        'accommodation': '-'
    })

    result = {
        'plan': plan,
        'tool_called': tools_used
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2)

    return result


def validate_itinerary(output_path, budget=None):
    """Validate the generated itinerary structure."""
    with open(output_path, 'r') as f:
        data = json.load(f)

    errors = []

    if 'plan' not in data:
        errors.append('Missing plan key')
    if 'tool_called' not in data:
        errors.append('Missing tool_called key')

    plan = data.get('plan', [])
    for day in plan:
        d = day.get('day')
        for k in ['day', 'current_city', 'transportation', 'breakfast',
                   'lunch', 'dinner', 'attraction', 'accommodation']:
            if k not in day:
                errors.append(f'Day {d}: missing key {k}')

    # Check no duplicate restaurants
    all_meals = []
    for day in plan:
        for mk in ['breakfast', 'lunch', 'dinner']:
            meal = day.get(mk, '-')
            if meal != '-':
                all_meals.append(meal)
    from collections import Counter
    for meal, count in Counter(all_meals).items():
        if count > 1:
            errors.append(f'Duplicate restaurant: {meal} used {count} times')

    if errors:
        print('VALIDATION ERRORS:')
        for e in errors:
            print(f'  - {e}')
    else:
        print('Validation passed!')

    return errors
