# KNOWN ISSUES

- **D3 Design Debt:** `aspect_ratio` and `resolution` are opaque pass-through strings. The labels (e.g. `"16:9 Landscape"`, `"Fast Preview (384p - ~1-2 min)"`) are notebook UI vocabulary leaking into our contract. This is accepted as design debt per Module 8 specifications.
- **Artifact Storage:** Local file storage adapter uses local paths and simulated downloads; production deployment relies on Kaggle dataset version staging.
