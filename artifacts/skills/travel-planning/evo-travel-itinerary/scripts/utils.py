import pandas as pd
import os


def _get_data_dir():
    """Discover data directory at runtime."""
    candidates = ['/app/data', './data']
    for d in candidates:
        if os.path.isdir(d):
            return d
    raise FileNotFoundError('Data directory not found')


DATA_DIR = _get_data_dir()


def search_cities(state=None):
    """Search cities, optionally filtered by state."""
    cities_file = os.path.join(DATA_DIR, 'background', 'citySet_with_states.txt')
    cities = []
    with open(cities_file, 'r') as f:
        for line in f:
            parts = line.strip().split('\t')
            if len(parts) == 2:
                city, st = parts
                if state is None or st.lower() == state.lower():
                    cities.append({'city': city, 'state': st})
    return pd.DataFrame(cities)


def search_accommodations(city=None, exclusion_keywords=None, policy_column=None,
                          min_occupancy=1, max_price=None):
    """Search accommodations with filters.

    Args:
        city: Filter by city name
        exclusion_keywords: List of strings to exclude from the policy column
        policy_column: Column containing policy/rules text; if None, auto-discovered
        min_occupancy: Minimum occupancy required
        max_price: Maximum price filter
    """
    df = pd.read_csv(os.path.join(DATA_DIR, 'accommodations', 'clean_accommodations_2022.csv'))
    if city:
        df = df[df['city'] == city]
    if exclusion_keywords:
        if policy_column is None:
            # Auto-discover: find text columns that are not identity/location columns
            text_cols = [c for c in df.columns
                         if df[c].dtype == 'object' and c not in ['NAME', 'city', 'room type']]
            policy_column = text_cols[0] if text_cols else None
        if policy_column and policy_column in df.columns:
            for kw in exclusion_keywords:
                df = df[~df[policy_column].str.contains(kw, na=False, case=False)]
    if min_occupancy > 1:
        df = df[df['maximum occupancy'] >= min_occupancy]
    if max_price is not None:
        df = df[df['price'] <= max_price]
    return df


def search_restaurants(city=None, cuisine=None):
    """Search restaurants with optional city and cuisine filters."""
    df = pd.read_csv(os.path.join(DATA_DIR, 'restaurants', 'clean_restaurant_2022.csv'))
    if city:
        df = df[df['City'] == city]
    if cuisine:
        df = df[df['Cuisines'].str.contains(cuisine, na=False, case=False)]
    return df


def search_attractions(city=None):
    """Search attractions, optionally filtered by city."""
    df = pd.read_csv(os.path.join(DATA_DIR, 'attractions', 'attractions.csv'))
    if city:
        df = df[df['City'] == city]
    return df


def search_distances(origin=None, destination=None):
    """Search driving distances between cities."""
    df = pd.read_csv(os.path.join(DATA_DIR, 'googleDistanceMatrix', 'distance.csv'))
    if origin:
        df = df[df['origin'] == origin]
    if destination:
        df = df[df['destination'] == destination]
    return df


def search_flights(origin=None, destination=None, date=None):
    """Search flights."""
    df = pd.read_csv(os.path.join(DATA_DIR, 'flights', 'clean_Flights_2022.csv'))
    if origin:
        col = 'OriginCityName' if 'OriginCityName' in df.columns else 'Origin'
        df = df[df[col] == origin]
    if destination:
        col = 'DestCityName' if 'DestCityName' in df.columns else 'Destination'
        df = df[col == destination]
    if date:
        col = 'FlightDate' if 'FlightDate' in df.columns else 'Date'
        if col in df.columns:
            df = df[df[col] == date]
    return df


def get_cheapest_accommodation(city, exclusion_keywords=None, policy_column=None,
                               min_occupancy=2, min_nights_max=None,
                               preferred_room_type=None):
    """Get cheapest accommodation in a city matching constraints.

    Args:
        city: City name
        exclusion_keywords: List of policy keywords to exclude
        policy_column: Column name for policy text (auto-discovered if None)
        min_occupancy: Minimum occupancy
        min_nights_max: Maximum allowed minimum-nights value
        preferred_room_type: If set, prefer this room type but fall back to any
    """
    acc = search_accommodations(
        city=city, exclusion_keywords=exclusion_keywords,
        policy_column=policy_column, min_occupancy=min_occupancy
    )
    if min_nights_max is not None:
        filtered = acc[acc['minimum nights'] <= min_nights_max]
        if len(filtered) > 0:
            acc = filtered
    if preferred_room_type and len(acc) > 0:
        preferred = acc[acc['room type'] == preferred_room_type]
        if len(preferred) > 0:
            return preferred.sort_values('price').iloc[0]
    return acc.sort_values('price').iloc[0] if len(acc) > 0 else None


def get_restaurants_by_cuisine(city, cuisine):
    """Get restaurants in a city serving a specific cuisine."""
    return search_restaurants(city=city, cuisine=cuisine)
