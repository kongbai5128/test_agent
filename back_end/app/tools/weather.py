"""
weather 工具 - 使用 Open-Meteo 查询真实城市天气。

Open-Meteo 的天气、地理编码和空气质量接口均不需要 API Key。
"""
from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .registry import ToolSpec, register

_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
_TIMEOUT_SECONDS = 10

_WEATHER_CODES = {
    0: "晴",
    1: "大部晴朗",
    2: "局部多云",
    3: "阴",
    45: "雾",
    48: "霜雾",
    51: "小毛毛雨",
    53: "中等毛毛雨",
    55: "大毛毛雨",
    56: "冻毛毛雨",
    57: "强冻毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "冻雨",
    67: "强冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "雪粒",
    80: "小阵雨",
    81: "中等阵雨",
    82: "强阵雨",
    85: "小阵雪",
    86: "强阵雪",
    95: "雷暴",
    96: "雷暴伴小冰雹",
    99: "雷暴伴大冰雹",
}

_WIND_DIRECTIONS = ["北风", "东北风", "东风", "东南风", "南风", "西南风", "西风", "西北风"]


def _fetch_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    query = urlencode(params)
    request = Request(
        f"{url}?{query}",
        headers={"User-Agent": "xiamen-guangchen-agent-weather/1.0"},
    )
    with urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return json.loads(response.read().decode(charset))


def _first_present(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value is not None:
            return value
    return None


def _fmt_number(value: Any, digits: int = 1) -> str:
    if value is None:
        return "暂无"
    if isinstance(value, (int, float)):
        return f"{value:.{digits}f}".rstrip("0").rstrip(".")
    return str(value)


def _weather_text(code: Any) -> str:
    try:
        return _WEATHER_CODES.get(int(code), f"未知天气代码 {code}")
    except (TypeError, ValueError):
        return "暂无"


def _wind_direction(degrees: Any) -> str:
    if degrees is None:
        return "暂无"
    try:
        index = round((float(degrees) % 360) / 45) % 8
    except (TypeError, ValueError):
        return "暂无"
    return _WIND_DIRECTIONS[index]


def _aqi_level(aqi: Any) -> str:
    if aqi is None:
        return "暂无"
    try:
        value = float(aqi)
    except (TypeError, ValueError):
        return str(aqi)
    if value <= 50:
        return "优"
    if value <= 100:
        return "良"
    if value <= 150:
        return "轻度污染"
    if value <= 200:
        return "中度污染"
    if value <= 300:
        return "重度污染"
    return "严重污染"


def _resolve_city(city: str) -> dict[str, Any] | None:
    data = _fetch_json(
        _GEOCODING_URL,
        {
            "name": city,
            "count": 5,
            "language": "zh",
            "format": "json",
        },
    )
    results = data.get("results") or []
    if not results:
        return None

    # 中文城市名优先选中国结果；英文/海外城市仍可使用 Open-Meteo 排序的第一项。
    for item in results:
        if item.get("country_code") == "CN":
            return item
    return results[0]


def _location_label(location: dict[str, Any]) -> str:
    parts = [
        location.get("name"),
        location.get("admin1"),
        location.get("country"),
    ]
    return "，".join(str(part) for part in parts if part)


def _get_current_weather(latitude: float, longitude: float) -> dict[str, Any]:
    return _fetch_json(
        _FORECAST_URL,
        {
            "latitude": latitude,
            "longitude": longitude,
            "current": ",".join(
                [
                    "temperature_2m",
                    "relative_humidity_2m",
                    "apparent_temperature",
                    "weather_code",
                    "wind_speed_10m",
                    "wind_direction_10m",
                    "wind_gusts_10m",
                ]
            ),
            "timezone": "auto",
            "forecast_days": 1,
        },
    )


def _get_air_quality(latitude: float, longitude: float) -> dict[str, Any] | None:
    try:
        return _fetch_json(
            _AIR_QUALITY_URL,
            {
                "latitude": latitude,
                "longitude": longitude,
                "current": "us_aqi,pm2_5,pm10",
                "timezone": "auto",
            },
        )
    except Exception:
        return None


def _weather(params: dict) -> str:
    city = str(params.get("city", "")).strip()
    if not city:
        return "错误：请提供城市名称"

    location = _resolve_city(city)
    if location is None:
        return f"错误：未找到城市 '{city}'，请换成更明确的城市名，例如：南京、北京市、上海"

    latitude = location.get("latitude")
    longitude = location.get("longitude")
    if latitude is None or longitude is None:
        return f"错误：城市 '{city}' 缺少经纬度信息，无法查询天气"

    weather_data = _get_current_weather(float(latitude), float(longitude))
    current = weather_data.get("current") or {}
    units = weather_data.get("current_units") or {}
    timezone = weather_data.get("timezone") or location.get("timezone") or ""

    air_data = _get_air_quality(float(latitude), float(longitude))
    air_current = (air_data or {}).get("current") or {}
    air_units = (air_data or {}).get("current_units") or {}

    temperature = current.get("temperature_2m")
    apparent = current.get("apparent_temperature")
    humidity = current.get("relative_humidity_2m")
    weather_code = current.get("weather_code")
    wind_speed = current.get("wind_speed_10m")
    wind_gusts = current.get("wind_gusts_10m")
    wind_degrees = current.get("wind_direction_10m")
    aqi = _first_present(air_current, "us_aqi", "european_aqi")
    pm25 = air_current.get("pm2_5")
    pm10 = air_current.get("pm10")

    temp_unit = units.get("temperature_2m", "°C")
    humidity_unit = units.get("relative_humidity_2m", "%")
    wind_unit = units.get("wind_speed_10m", "km/h")
    aqi_unit = _first_present(air_units, "us_aqi", "european_aqi") or "AQI"
    pm25_unit = air_units.get("pm2_5", "μg/m³")
    pm10_unit = air_units.get("pm10", "μg/m³")

    return (
        f"📍 {_location_label(location)} 当前天气（实时数据，Open-Meteo）\n"
        f"更新时间：{current.get('time', '暂无')} {timezone}\n"
        f"天气状况：{_weather_text(weather_code)}\n"
        f"温度：{_fmt_number(temperature)}{temp_unit}（体感 {_fmt_number(apparent)}{temp_unit}）\n"
        f"湿度：{_fmt_number(humidity, 0)}{humidity_unit}\n"
        f"风向风速：{_wind_direction(wind_degrees)} {_fmt_number(wind_speed)} {wind_unit}"
        f"（阵风 {_fmt_number(wind_gusts)} {wind_unit}）\n"
        f"空气质量：{_aqi_level(aqi)}（{_fmt_number(aqi, 0)} {aqi_unit}，"
        f"PM2.5 {_fmt_number(pm25)} {pm25_unit}，PM10 {_fmt_number(pm10)} {pm10_unit}）"
    )


register(
    ToolSpec(
        name="weather",
        description=(
            "查询城市实时天气信息（真实数据，来源 Open-Meteo），包括天气状况、温度、体感温度、"
            "湿度、风向风速和空气质量。支持中文或英文城市名，例如：南京、北京、上海、London。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "城市名称，例如：'南京'、'北京'、'上海'、'London'",
                }
            },
            "required": ["city"],
        },
        handler=_weather,
    )
)
