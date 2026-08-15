"""Select accommodations for each city based on caller-supplied constraints."""
import sys
sys.path.insert(0, '/app/environment/skills/evo-travel-itinerary/scripts')
from utils import get_cheapest_accommodation


def select_accommodation_for_city(city, exclusion_keywords=None, policy_column=None,
                                   min_occupancy=2, max_min_nights=2,
                                   preferred_room_type=None):
    """Select the cheapest accommodation in a city matching constraints.

    Args:
        city: City name
        exclusion_keywords: List of policy keywords to exclude (caller-supplied)
        policy_column: Column containing policy text (auto-discovered if None)
        min_occupancy: Minimum occupancy required
        max_min_nights: Maximum allowed minimum-nights value
        preferred_room_type: If set, prefer this room type but fall back to any
    """
    result = get_cheapest_accommodation(
        city=city,
        exclusion_keywords=exclusion_keywords,
        policy_column=policy_column,
        min_occupancy=min_occupancy,
        min_nights_max=max_min_nights,
        preferred_room_type=preferred_room_type
    )
    return result
