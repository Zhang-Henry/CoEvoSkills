import pandas as pd
import os

def _get_data_dir():
    """Discover data directory at runtime."""
    candidates = ['/app/data', './data']
    for d in candidates:
        if os.path.isdir(d):
            return d
    raise FileNotFoundError('Data directory not found')

def search_cities(state=None, data_dir=None):
    """Search for cities, optionally filtered by state."""
    if data_dir is None:
        data_dir = _get_data_dir()
    cities_file = os.path.join(data_dir, 'background', 'citySet_with_states.txt')
    results = []
    with open(cities_file, 'r') as f:
        for line in f:
            parts = line.strip().split('\t')
            if len(parts) == 2:
                city, st = parts
                if state is None or st.lower() == state.lower():
                    results.append({'city': city, 'state': st})
    return results

def search_accommodations(city=None, exclusion_keywords=None, policy_column=None,
                          min_occupancy=1, max_price=None, data_dir=None):
    """Search accommodations with filters.
    
    Args:
        city: Filter by city name
        exclusion_keywords: List of strings; exclude rows where policy_column contains any of these
        policy_column: Column name containing policy/rules text (discovered at runtime if None)
        min_occupancy: Minimum occupancy required
        max_price: Maximum price filter
        data_dir: Data directory path
    """
    if data_dir is None:
        data_dir = _get_data_dir()
    df = pd.read_csv(os.path.join(data_dir, 'accommodations', 'clean_accommodations_2022.csv'))
    if city:
        df = df[df['city'] == city]
    if exclusion_keywords and policy_column:
        for kw in exclusion_keywords:
            df = df[~df[policy_column].str.contains(kw, case=False, na=False)]
    elif exclusion_keywords:
        # Auto-discover policy column: look for text columns with rule-like content
        text_cols = [c for c in df.columns if df[c].dtype == 'object' and c not in ['NAME', 'city', 'room type']]
        for col in text_cols:
            for kw in exclusion_keywords:
                df = df[~df[col].str.contains(kw, case=False, na=False)]
    if min_occupancy > 1:
        df = df[df['maximum occupancy'] >= min_occupancy]
    if max_price:
        df = df[df['price'] <= max_price]
    return df.to_dict('records')

def search_restaurants(city=None, cuisine=None, data_dir=None):
    """Search restaurants, optionally filtered by city and cuisine type."""
    if data_dir is None:
        data_dir = _get_data_dir()
    df = pd.read_csv(os.path.join(data_dir, 'restaurants', 'clean_restaurant_2022.csv'))
    if city:
        df = df[df['City'] == city]
    if cuisine:
        df = df[df['Cuisines'].str.contains(cuisine, case=False, na=False)]
    return df.to_dict('records')

def search_attractions(city=None, data_dir=None):
    """Search attractions by city."""
    if data_dir is None:
        data_dir = _get_data_dir()
    df = pd.read_csv(os.path.join(data_dir, 'attractions', 'attractions.csv'))
    if city:
        df = df[df['City'] == city]
    return df.to_dict('records')

def search_distances(origin=None, destination=None, data_dir=None):
    """Search driving distances between cities."""
    if data_dir is None:
        data_dir = _get_data_dir()
    df = pd.read_csv(os.path.join(data_dir, 'googleDistanceMatrix', 'distance.csv'))
    if origin:
        df = df[df['origin'] == origin]
    if destination:
        df = df[df['destination'] == destination]
    return df.to_dict('records')

def search_flights(origin=None, destination=None, date=None, data_dir=None):
    """Search flights."""
    if data_dir is None:
        data_dir = _get_data_dir()
    df = pd.read_csv(os.path.join(data_dir, 'flights', 'clean_Flights_2022.csv'))
    if origin:
        df = df[df['OriginCityName'] == origin]
    if destination:
        df = df[df['DestCityName'] == destination]
    if date:
        df = df[df['FlightDate'] == date]
    return df.to_dict('records')
