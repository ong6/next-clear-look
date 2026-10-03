# Data sources, attribution and licences

Next Clear Look keeps source identity and attribution in the fixture manifest and exposes the
same text through `/v1/attributions`. Attribution is evidence, not decorative footer copy.

| Source | Use | Attribution | Terms |
|---|---|---|---|
| CelesTrak | Sentinel-2 OMM orbital elements | `Orbital elements: CelesTrak, retrieved <date> UTC.` | [CelesTrak usage policy](https://celestrak.org/usage-policy.php); cache each group for at least two hours and do not bulk mirror |
| Earth Search by Element 84 | Sentinel-2 L2A catalogue | `Catalogue: Earth Search by Element 84.` | [Earth Search](https://github.com/Element84/earth-search); public best-effort API |
| Copernicus Sentinel data | SCL evidence and true-colour crops | `Contains modified Copernicus Sentinel data <year>.` | [Sentinel Data Legal Notice](https://dataspace.copernicus.eu/terms-and-conditions) |
| JPL DE421 | Earth/Sun ephemeris for illumination | `Ephemeris: JPL DE421 (2023–2027 excerpt).` | [JPL Solar System Dynamics](https://ssd.jpl.nasa.gov/planets/eph_export.html); NASA/JPL source acknowledgement |
| NASA Blue Marble NG | Bundled daytime globe imagery | `NASA Blue Marble` | NASA imagery; public-domain U.S. government work unless separately noted |
| NASA Black Marble 2012 | Bundled night-side globe imagery | `NASA Black Marble 2012` | NASA imagery; public-domain U.S. government work unless separately noted |
| EOX Sentinel-2 cloudless 2024 | Optional live close-zoom basemap | `Sentinel-2 cloudless – https://s2maps.eu by EOX IT Services GmbH (Contains modified Copernicus Sentinel data 2024)` | CC BY-NC-SA 4.0; online enhancement only |

The checked-in DE421 excerpt is generated from the `de421.bsp` distributed in
`skyfield-data==7.0.0`; its reproducible command and retained target segments are documented in
[`fixtures/ephemeris/README.md`](../fixtures/ephemeris/README.md). The application uses
`load.timescale(builtin=True)` and never downloads an ephemeris at runtime.

Fixture recordings contain only public, keyless source responses. The recorder rejects signed
URLs and strips credentials, cookies, tracing IDs and other non-allowlisted headers before data
can enter Git.
