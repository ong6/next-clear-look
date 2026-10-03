# DE421 replay excerpt

Replay uses a bounded JPL DE421 SPK excerpt for Earth/Sun geometry. It covers
`2023-01-01T00:00:00Z` through `2028-01-01T00:00:00Z` (the end is exclusive), which is the
2023–2027 window the engine needs, so it never downloads an ephemeris at runtime. The retained SPK target segments are:

- solar-system barycentre (0) to Earth barycentre (3);
- solar-system barycentre (0) to Jupiter barycentre (5);
- solar-system barycentre (0) to Saturn barycentre (6);
- solar-system barycentre (0) to Sun (10);
- Earth barycentre (3) to Earth (399).

The content-addressed blob and its digest are declared in `fixtures/fixture-set.json`. It was
produced with `jplephem==2.24` from the `de421.bsp` distributed by `skyfield-data==7.0.0`:

```bash
uv run --with jplephem==2.24 --with skyfield-data==7.0.0 \
  python tools/build_ephemeris.py \
  --source /path/to/site-packages/skyfield_data/data/de421.bsp
```

The builder accepts only a local source path; it never downloads at runtime. To inspect the
result:

```bash
uv run --with jplephem==2.24 python -m jplephem spk \
  fixtures/blobs/sha256/fb/fb18986a9f2a5bf510b597f5c446c9c257c8e2fc79396060e881a24897243af1
```

JPL ephemerides are produced by NASA's Jet Propulsion Laboratory. NASA content is generally not
subject to copyright in the United States; see the attribution and usage notes in
`docs/attribution.md`.
