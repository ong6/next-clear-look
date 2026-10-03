# Bundled globe imagery

These files are downloaded once and served locally so recorded replay never depends on a map
service. The complete directory is 11,940,729 bytes (under the 12 MB bundled-imagery budget).

## Sources and rights

| Files | Source | Use | Licence / credit |
|---|---|---|---|
| `world.topo.bathy.200410.3x5400x2700.jpg`, `presets/*-200410.jpg` | [NASA Blue Marble: Next Generation with Topography and Bathymetry](https://science.nasa.gov/earth/earth-observatory/blue-marble-next-generation/base-topography-bathymetry/), October 2004 | Day side and close regional context | NASA imagery is generally not copyrighted in the United States. Credit NASA Earth Observatory / Blue Marble: Next Generation. |
| `dnb_land_ocean_ice.2012.3600x1800.jpg` | [NASA Visible Earth — Night Lights 2012 Map](https://visibleearth.nasa.gov/images/79765/night-lights-2012-map) | Night side | NASA imagery is generally not copyrighted in the United States. Credit NASA Earth Observatory / Black Marble. |

The global October image comes from NASA's 5,400×2,700 direct JPEG. Each 4,800×4,800 preset
image is a 20°×20° crop from the corresponding October 2004 21,600×21,600 source tiles. Those
tiles form an 86,400×43,200 equirectangular world at 15 arc-seconds per pixel (nominal 500 m at
the equator). Crops crossing 0° longitude, 90° E, or the equator were joined without resampling.
The committed crops were JPEG-compressed after the pixel crop; their dimensions were not reduced.

| Preset crop | Geographic bounds (W, S, E, N) | NASA source tiles |
|---|---|---|
| `singapore-coast-200410.jpg` | 93.695, -8.700, 113.695, 11.300 | NASA tiles row D columns 1–2 |
| `rotterdam-port-200410.jpg` | -5.960, 41.935, 14.040, 61.935 | NASA tiles B1 and C1 |
| `atacama-works-200410.jpg` | -78.235, -33.520, -58.235, -13.520 | NASA tile B2 |
| `sundarbans-delta-200410.jpg` | 79.425, 11.850, 99.425, 31.850 | NASA row C column 1 and row D column 1 tiles |
| `jakobshavn-front-200410.jpg` | -60.675, 59.200, -40.675, 79.200 | NASA tile B1 |

The direct source pattern is:

`https://assets.science.nasa.gov/content/dam/science/esd/eo/images/bmng/bmng-topography-bathymetry/october/world.topo.bathy.200410.3x21600x21600.{tile}.jpg`

## SHA-256

- Global October Blue Marble: `f9ad745c780281dbfdda9769f10b161aacb0a03c83888ab24d4be16575aa4a7c`
- Black Marble: `373e5a08c9f378a2ce6320214a613148e4b1e3946b3f39a516c9093b76cb7124`
- Atacama: `75b75a01c0378a18885ddf50981481b327d868b1d78046b0f3bfa4d8e0ba3b2a`
- Jakobshavn: `3fa31e2713540f6ff585efd88cfaa2faa2418256053abb9fc2d54dbe9b1440fa`
- Rotterdam: `2a3960e8aa93a8dcd5f55f991269d86c767bec7cb06a3ea2acbac87c307a7d5c`
- Singapore: `75bff8e1007c52fd51d2a2e2d17ded4e664d494b6f5fa2d305032fbdc43e1062`
- Sundarbans: `3d7c23ff2db386b762844882f32f8df1a93db469c0abba7ceae4909c86910a49`
