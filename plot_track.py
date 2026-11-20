import numpy as np
import pandas as pd
import folium
from branca.colormap import LinearColormap

CSV_PATH = r"loures_ubbo\ccLoures_ccUbbo_raw_Data.csv"
OUT_SPEED_HTML = "track_map_speed.html"
OUT_ALT_HTML = "track_map_altitude.html"
SUBDIVISIONS = 8 # # pieces per GPS segment -> smoothness of the gradient
MAX_SPEED_PERCENTILE = 100 # use e.g. 98 to stop one GPS spike from stretching the scale
ALT_SMOOTH_WINDOW = 1  # GPS altitude is noisy; try 5 to 11 to smooth it (1 = off)

# Colour ramps (RGB), evenly spaced from lowest to highest value
SPEED_COLORS = [(255, 0, 0), (0, 0, 255)] # stopped -> fastest
ALT_COLORS = [(30, 140, 50), (240, 220, 70), (120, 70, 30)] # low (green) -> yellow -> high (brown)


# 1. Load and clean
df = pd.read_csv(CSV_PATH, encoding="utf-8")
df.columns = [c.strip() for c in df.columns]

# Find columns by prefix, so it doesn't matter whether the header has "°", "º" or "Â°"
lat = next(c for c in df.columns if c.startswith("Latitude"))
lon = next(c for c in df.columns if c.startswith("Longitude"))
spd = next(c for c in df.columns if c.startswith("Speed"))
alt = next(c for c in df.columns if c.startswith("Altitude (m)"))

df = df.dropna(subset=[lat, lon]).copy()
df[spd] = df[spd].interpolate().bfill().ffill()   # the speed column contains NaNs
df[alt] = df[alt].interpolate().bfill().ffill()

if ALT_SMOOTH_WINDOW > 1:
    df[alt] = df[alt].rolling(ALT_SMOOTH_WINDOW, center=True, min_periods=1).median()

pts = df[[lat, lon]].to_numpy()


# 2. Helpers
def make_color_fn(colors):
    colors = np.array(colors, float)
    xs = np.linspace(0, 1, len(colors))

    def fn(t):
        t = np.clip(t, 0, 1)
        return tuple(int(np.interp(t, xs, colors[:, c])) for c in range(3))
    return fn

def rgb_to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(*rgb)

def build_map(values, v_min, v_max, colors, caption, out_html, legend_factor=1.0):
    to_rgb = make_color_fn(colors)

    m = folium.Map(
        location=[df[lat].mean(), df[lon].mean()],
        zoom_start=14,
        tiles="OpenStreetMap"
    )

    # Each GPS segment is split into small pieces whose colour is interpolated
    # between the value at the start and the value at the end of the segment.
    for i in range(len(pts) - 1):
        for k in range(SUBDIVISIONS):
            f0, f1 = k / SUBDIVISIONS, (k + 1) / SUBDIVISIONS
            p0 = pts[i] + f0 * (pts[i + 1] - pts[i])
            p1 = pts[i] + f1 * (pts[i + 1] - pts[i])
            v_mid = values[i] + (f0 + f1) / 2 * (values[i + 1] - values[i])
            t = (v_mid - v_min) / (v_max - v_min)

            folium.PolyLine(
                [p0.tolist(), p1.tolist()],
                color=rgb_to_hex(to_rgb(t)),
                weight=5,
                opacity=0.9,
            ).add_to(m)

    # Start / end markers
    folium.Marker(pts[0].tolist(), tooltip="Start", icon=folium.Icon(color="green")).add_to(m)
    folium.Marker(pts[-1].tolist(), tooltip="End", icon=folium.Icon(color="black")).add_to(m)

    # Legend
    legend = LinearColormap([rgb_to_hex(c) for c in colors],
                            vmin=v_min * legend_factor, vmax=v_max * legend_factor,
                            caption=caption)
    legend.add_to(m)

    m.fit_bounds([pts.min(axis=0).tolist(), pts.max(axis=0).tolist()])
    m.save(out_html)


# 3. Speed map (red = stopped, blue = fastest)
vel = df[spd].to_numpy()
v_max = np.percentile(vel, MAX_SPEED_PERCENTILE)
build_map(vel, 0.0, v_max, SPEED_COLORS, "Speed (km/h)", OUT_SPEED_HTML, legend_factor=3.6)
print(f"Saved {OUT_SPEED_HTML}  (speed range 0 - {v_max:.1f} m/s = {v_max*3.6:.0f} km/h)")


# 4. Altitude map (green = lowest, yellow = middle, brown = highest)
h = df[alt].to_numpy()
h_min, h_max = h.min(), h.max()
build_map(h, h_min, h_max, ALT_COLORS, "Altitude (m)", OUT_ALT_HTML)
print(f"Saved {OUT_ALT_HTML}  (altitude range {h_min:.0f} - {h_max:.0f} m)")