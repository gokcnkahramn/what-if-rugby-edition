from rugby_sim.data.sources.historical_weather import classify_weather, fetch_historical_weather


def test_classify_weather_thresholds():
    assert classify_weather(None) == "dry"
    assert classify_weather({"precipitation_sum": 0.1, "wind_speed_10m_max": 10.0}) == "dry"
    assert classify_weather({"precipitation_sum": 5.0, "wind_speed_10m_max": 5.0}) == "wet"
    assert classify_weather({"precipitation_sum": 0.0, "wind_speed_10m_max": 45.0}) == "windy"
    # Wet takes priority over windy when both thresholds are crossed.
    assert classify_weather({"precipitation_sum": 5.0, "wind_speed_10m_max": 45.0}) == "wet"


def test_fetch_historical_weather_returns_real_data_for_a_known_date():
    # 1995 Rugby World Cup Final, Ellis Park, Johannesburg - a real, known
    # date/location, live-fetched (disk-cached after the first real call).
    weather = fetch_historical_weather(-26.1853, 28.0609, "1995-06-24")
    assert weather is not None
    assert "temperature_2m_max" in weather
    assert "precipitation_sum" in weather
    assert isinstance(weather["temperature_2m_max"], (int, float))
    assert classify_weather(weather) in ("dry", "wet", "windy")
